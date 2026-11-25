from __future__ import annotations

import json
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .limits import ServiceGuard
from .topics_data import Topic

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_LT_URL = "https://api.languagetool.org/v2/check"
DEFAULT_TR_URL = "https://api.mymemory.translated.net/get"
RECOMMENDED_MODEL = "qwen2.5:1.5b"
PREFERRED_MODELS = ("qwen2.5:1.5b", "llama3.2:1b", "qwen2.5:0.5b", "llama3.2:3b", "qwen2.5:3b")


class AIError(Exception):
    pass


def _request_json(url: str, *, payload: dict | None = None, form: dict | None = None,
                  timeout: float = 10, use_proxy: bool = True) -> dict:
    headers = {"User-Agent": "EnglishTrainer/1.0"}
    data = None
    if form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    opener = urllib.request.build_opener() if use_proxy else urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise AIError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise AIError(str(exc)) from exc


# --------------------------------------------------------------------- Ollama
class OllamaClient:
    def __init__(self, url: str = DEFAULT_OLLAMA_URL):
        self.url = (url or DEFAULT_OLLAMA_URL).rstrip("/")

    def models(self, timeout: float = 1.5) -> list[str] | None:
        """Список встановлених моделей або None, якщо Ollama не запущено."""
        try:
            data = _request_json(f"{self.url}/api/tags", timeout=timeout, use_proxy=False)
        except AIError:
            return None
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def chat(self, model: str, messages: list[dict], timeout: float = 180) -> str:
        data = _request_json(
            f"{self.url}/api/chat",
            payload={"model": model, "messages": messages, "stream": False,
                     "options": {"temperature": 0.7, "num_predict": 110}},
            timeout=timeout, use_proxy=False,
        )
        text = (data.get("message") or {}).get("content", "")
        if not text.strip():
            raise AIError("Порожня відповідь моделі")
        return text


def choose_model(models: list[str], saved: str = "") -> str | None:
    if saved and saved in models:
        return saved
    for pref in PREFERRED_MODELS:
        for m in models:
            if m == pref or m.startswith(pref):
                return m
    return models[0] if models else None


# ---------------------------------------------------------------- LanguageTool
@dataclass
class Issue:
    wrong: str
    suggestion: str
    message: str


@dataclass
class Correction:
    original: str
    corrected: str
    issues: list[Issue]


class LanguageToolClient:
    SKIP_CATEGORIES = {"TYPOGRAPHY", "STYLE", "PLAIN_ENGLISH", "REDUNDANCY"}

    def __init__(self, url: str = DEFAULT_LT_URL, guard: ServiceGuard | None = None):
        self.url = url or DEFAULT_LT_URL
        self.guard = guard

    def check(self, text: str) -> Correction:
        if self.guard is not None:
            self.guard.acquire(len(text))
        try:
            data = _request_json(self.url, form={"text": text, "language": "en-US", "motherTongue": "uk"}, timeout=8)
        except AIError as exc:
            if self.guard is not None and "429" in str(exc):
                self.guard.penalize(60)
            raise
        matches = [
            m for m in data.get("matches", [])
            if m.get("replacements") and (m.get("rule") or {}).get("category", {}).get("id") not in self.SKIP_CATEGORIES
        ]
        matches.sort(key=lambda m: m["offset"])
        corrected, limit, issues = text, len(text), []
        for m in reversed(matches):
            start, end = m["offset"], m["offset"] + m["length"]
            if end > limit:
                continue
            suggestion = m["replacements"][0]["value"]
            issues.append(Issue(text[start:end], suggestion, m.get("message", "")))
            corrected = corrected[:start] + suggestion + corrected[end:]
            limit = start
        issues.reverse()
        return Correction(text, corrected, issues)

def fit_bytes(text: str, limit: int = 450) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= limit:
        return text
    cut = raw[:limit].decode("utf-8", "ignore")
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[: end + 1] if end > 0 else cut


class TranslatorClient:
    def __init__(self, url: str = DEFAULT_TR_URL, guard: ServiceGuard | None = None):
        self.url = url or DEFAULT_TR_URL
        self.guard = guard

    def translate(self, text: str, src: str = "en", dst: str = "uk") -> str:
        text = fit_bytes(text)
        if self.guard is not None:
            self.guard.acquire(len(text))
        query = urllib.parse.urlencode({"q": text, "langpair": f"{src}|{dst}"})
        sep = "&" if "?" in self.url else "?"
        try:
            data = _request_json(f"{self.url}{sep}{query}", timeout=8)
            if str(data.get("responseStatus", "200")) != "200":
                raise AIError(f"HTTP {data.get('responseStatus')}: {data.get('responseDetails', '')}")
            out = (data.get("responseData") or {}).get("translatedText", "").strip()
            if "MYMEMORY WARNING" in out.upper():  # денну квоту вичерпано
                raise AIError("HTTP 429: quota exceeded")
        except AIError as exc:
            if self.guard is not None and "429" in str(exc):
                self.guard.exhaust_today()
            raise
        if not out:
            raise AIError("Порожній переклад")
        return out


_HELP_RE = re.compile(
    r"(don'?t|do not|didn'?t|can'?t|cannot)\s+(understand|get)|\btranslat|\brepeat\b|what do you mean|"
    r"what does .{1,30} mean|\bsay (it )?again\b|\bnot clear\b|\bhelp\b",
    re.IGNORECASE,
)
_CYRILLIC_RE = re.compile("[А-Яа-яІіЇїЄєҐґ]")


def is_help_request(text: str) -> bool:
    return bool(_HELP_RE.search(text)) or bool(_CYRILLIC_RE.search(text))


# -------------------------------------------------------------------- Partner
ACKS = ["I see.", "That's interesting.", "That makes sense.", "Thanks for sharing that.", "Good point.", "Nice."]
FOLLOWUPS = [
    "Why is that?", "Can you give me an example?", "How do you feel about it?",
    "Can you tell me more about that?", "How often does this happen in your life?",
    "Is that important to you? Why?", "What is the best thing about it?",
    "And is there anything you dislike about it?", "How was it in the past?",
    "Would you like it to change in the future?",
]
NUDGES = [
    "Could you say a little more? Try to answer in two or three full sentences.",
    "Please tell me more. Two or three sentences will help you practise.",
]
LEVEL_HINTS = {
    "A2": "Use very simple words and short sentences.",
    "B1": "Use common vocabulary and clear sentences.",
    "B2": "Use natural everyday English; you may use some idioms.",
    "C1": "Use natural, richer English and challenge the learner's opinions politely.",
}


class Partner:
    def __init__(self, topic: Topic, level: str, client: OllamaClient | None = None,
                 model: str | None = None, rng: random.Random | None = None):
        self.topic, self.level = topic, level
        self.client, self.model = (client, model) if client and model else (None, None)
        self.rng = rng or random.Random()
        self.history: list[dict] = [{"role": "assistant", "content": topic.question}]
        self.fell_back = False
        self.help_requested = False
        self.last_question = topic.question
        self._pool: list[str] = []

    @property
    def system_prompt(self) -> str:
        return (
            "You are a friendly English conversation partner helping a learner practise speaking. "
            f"The topic is: {self.topic.title}. {LEVEL_HINTS.get(self.level, '')} "
            "Reply in English only, in 1 to 3 short sentences. React to what the learner said, "
            "then ask exactly ONE follow-up question. Do not correct mistakes. "
            "Do not use lists, markdown, emojis or quotation marks."
        )

    def reply(self, user_text: str) -> str:
        self.history.append({"role": "user", "content": user_text})
        self.help_requested = is_help_request(user_text)
        if self.help_requested:  # не зрозумів — повторюємо питання, без вигаданих реакцій
            text = f"No problem! Let me ask again: {self.last_question}"
            self.history.append({"role": "assistant", "content": text})
            return text
        text = None
        if self.client and self.model and not self.fell_back:
            try:
                msgs = [{"role": "system", "content": self.system_prompt}] + self.history[-12:]
                text = self._clean(self.client.chat(self.model, msgs))
            except AIError:
                self.fell_back = True  # далі працюємо в керованому режимі
        if not text:
            text = self._guided(user_text)
        self.history.append({"role": "assistant", "content": text})
        self.last_question = text
        return text

    @staticmethod
    def _clean(text: str) -> str:
        text = re.sub(r"[*#_`>]+", "", text)
        return re.sub(r"\s+", " ", text).strip()[:600]

    def _guided(self, user_text: str) -> str:
        if len(user_text.split()) < 4:
            return self.rng.choice(NUDGES)
        if not self._pool:
            self._pool = FOLLOWUPS[:]
            self.rng.shuffle(self._pool)
        return f"{self.rng.choice(ACKS)} {self._pool.pop()}"
