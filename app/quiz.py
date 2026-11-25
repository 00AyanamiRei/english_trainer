from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from .database import Verb, Word

EN2UK = "en2uk"
UK2EN = "uk2en"
LISTEN_WRITE = "listen_write"
LISTEN_TRANSLATE = "listen_translate"
SPELL = "spell"
QUIZ = "quiz"
VERB_FILL = "verb_fill"
VERB_TRANSLATE = "verb_translate"
VERB_LISTEN = "verb_listen"

QTYPE_NAMES = {
    EN2UK: "Переклад з англійської",
    UK2EN: "Переклад з української",
    LISTEN_WRITE: "Аудіювання: написання",
    LISTEN_TRANSLATE: "Аудіювання: переклад",
    SPELL: "Пошук помилки",
    QUIZ: "Квіз",
    VERB_FILL: "Дієслова: відсутні форми",
    VERB_TRANSLATE: "Дієслова: переклад",
    VERB_LISTEN: "Дієслова: аудіювання",
}

FORM_LABELS = ("V1 (Infinitive)", "V2 (Past Simple)", "V3 (Past Participle)")


_APOSTROPHES = str.maketrans({"’": "'", "ʼ": "'", "`": "'", "´": "'", "‘": "'"})


def normalize(text: str) -> str:
    t = text.translate(_APOSTROPHES).casefold().strip()
    t = re.sub(r"\s+", " ", t)
    return t.strip(" .,!?;:\"")


def _strip_parens(text: str) -> str:
    return re.sub(r"\s*\([^)]*\)", "", text).strip()


def _variants(text: str, splitter: str) -> list[str]:
    result: list[str] = []

    def add(value: str) -> None:
        value = value.strip()
        if value and value not in result:
            result.append(value)

    add(text)
    add(_strip_parens(text))
    for part in re.split(splitter, text):
        add(part)
        add(_strip_parens(part))
    return result


def translation_variants(text: str) -> list[str]:
    return _variants(text, r"[;,]")


def english_variants(text: str) -> list[str]:
    result = _variants(text, r"/")
    result += [v[3:].strip() for v in result if v.casefold().startswith("to ") and len(v) > 3]
    return result


def form_variants(text: str) -> list[str]:
    return _variants(text, r"[/,;]")


@dataclass
class Field:
    label: str
    accepted: list[str]
    display: str
    lang: str = "en"


@dataclass
class Question:
    qtype: str
    kind: str  # 'word' | 'verb'
    item_id: int
    instruction: str
    prompt: str = ""
    secondary: str = ""
    audio: str = ""
    fields: list[Field] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    correct_choice: int = -1
    correct_text: str = ""
    extra: str = ""

    @property
    def answer_text(self) -> str:
        if self.correct_text:
            return self.correct_text
        if self.fields:
            return " | ".join(f.display for f in self.fields)
        if 0 <= self.correct_choice < len(self.choices):
            return self.choices[self.correct_choice]
        return ""

    def describe(self) -> str:
        parts = [p for p in (self.prompt, self.secondary) if p]
        if self.audio:
            parts.insert(0, "🔊 (аудіо)")
        return " · ".join(parts)


@dataclass
class Evaluation:
    correct: bool
    field_ok: list[bool]
    user_answer: str
    correct_answer: str


@dataclass
class QuestionResult:
    question: Question
    evaluation: Evaluation


def evaluate(q: Question, answers: list[str]) -> Evaluation:
    if q.choices:
        try:
            idx = int(answers[0])
        except (IndexError, ValueError):
            idx = -1
        ok = idx == q.correct_choice
        user = q.choices[idx] if 0 <= idx < len(q.choices) else ""
        return Evaluation(ok, [ok], user, q.answer_text)

    answers = list(answers) + [""] * (len(q.fields) - len(answers))
    flags = []
    for f, a in zip(q.fields, answers):
        accepted = {normalize(v) for v in f.accepted}
        flags.append(normalize(a) in accepted)
    return Evaluation(all(flags), flags, " | ".join(a.strip() for a in answers[: len(q.fields)]), q.answer_text)


def mutate(text: str, rng: random.Random) -> str:
    letters = [i for i, c in enumerate(text) if c.isalpha()]
    if not letters:
        return text + "x"
    for _ in range(20):
        chars = list(text)
        i = rng.choice(letters)
        op = rng.choice(["swap", "drop", "double", "replace"])
        if op == "swap" and i + 1 < len(chars) and chars[i].isalpha() and chars[i + 1].isalpha():
            chars[i], chars[i + 1] = chars[i + 1], chars[i]
        elif op == "drop" and len(letters) > 3:
            del chars[i]
        elif op == "double":
            chars.insert(i, chars[i])
        elif op == "replace":
            chars[i] = rng.choice([c for c in "abcdefghijklmnopqrstuvwxyz" if c != chars[i].lower()])
        result = "".join(chars)
        if normalize(result) != normalize(text):
            return result
    return text + text[-1]


class QuestionGenerator:
    def __init__(self, words: list[Word], verbs: list[Verb], audio: bool = True, rng: random.Random | None = None):
        self.words = {w.id: w for w in words}
        self.verbs = {v.id: v for v in verbs}
        self.audio = audio
        self.rng = rng or random.Random()

    def build(self, kind: str, ids: list[int], count: int | None = None) -> list[Question]:
        ids = list(ids)
        count = count or len(ids)
        sequence: list[int] = []
        while len(sequence) < count:
            batch = ids[:]
            self.rng.shuffle(batch)
            if sequence and len(batch) > 1 and batch[0] == sequence[-1]:
                batch.append(batch.pop(0))
            sequence.extend(batch)
        make = self.word_question if kind == "word" else self.verb_question
        pool = self.words if kind == "word" else self.verbs
        return [make(pool[i]) for i in sequence[:count]]

    def _pick_distractors(self, candidates: list[str], correct: str, n: int = 3) -> list[str]:
        seen = {normalize(correct)}
        pool = candidates[:]
        self.rng.shuffle(pool)
        result = []
        for c in pool:
            key = normalize(c)
            if key and key not in seen:
                seen.add(key)
                result.append(c)
            if len(result) == n:
                break
        return result

    def _choice_question(self, qtype, kind, item_id, instruction, prompt, correct, distractors, extra="") -> Question:
        options = [correct] + distractors
        self.rng.shuffle(options)
        return Question(
            qtype, kind, item_id, instruction, prompt=prompt, choices=options,
            correct_choice=options.index(correct), extra=extra,
        )

    @staticmethod
    def _word_extra(w: Word) -> str:
        parts = []
        if w.transcription:
            parts.append(w.transcription)
        if w.example:
            parts.append(f"Приклад: {w.example}")
        return " · ".join(parts)

    def word_question(self, w: Word) -> Question:
        types = [EN2UK, UK2EN, SPELL, QUIZ]
        if self.audio:
            types += [LISTEN_WRITE, LISTEN_TRANSLATE]
        qtype = self.rng.choice(types)
        extra = self._word_extra(w)
        en_field = Field("Англійською", english_variants(w.english), w.english, "en")
        uk_field = Field("Українською", translation_variants(w.ukrainian), w.ukrainian, "uk")

        if qtype == EN2UK:
            return Question(qtype, "word", w.id, "Введіть український переклад", prompt=w.english,
                            fields=[uk_field], extra=extra)
        if qtype == UK2EN:
            return Question(qtype, "word", w.id, "Введіть слово англійською", prompt=w.ukrainian,
                            fields=[en_field], extra=extra)
        if qtype == LISTEN_WRITE:
            return Question(qtype, "word", w.id, "Прослухайте та напишіть слово англійською", audio=w.english,
                            fields=[en_field], extra=extra)
        if qtype == LISTEN_TRANSLATE:
            return Question(qtype, "word", w.id, "Прослухайте та введіть український переклад", audio=w.english,
                            fields=[uk_field], extra=extra)
        if qtype == SPELL:
            return self._spell(w, extra)
        q = self._quiz(w, extra)
        return q if q else Question(EN2UK, "word", w.id, "Введіть український переклад", prompt=w.english,
                                    fields=[uk_field], extra=extra)

    def _spell(self, w: Word, extra: str) -> Question:
        wrong = mutate(w.english, self.rng)
        if self.rng.random() < 0.5:  # Так / Ні
            show_wrong = self.rng.random() < 0.5
            return Question(
                SPELL, "word", w.id, "Чи є помилка в написанні англійського слова?",
                prompt=w.ukrainian, secondary=wrong if show_wrong else w.english,
                choices=["Так, є помилка", "Ні, помилки немає"],
                correct_choice=0 if show_wrong else 1,
                correct_text=f"Помилка є. Правильно: {w.english}" if show_wrong else "Помилки немає",
                extra=extra,
            )
        options = [w.english, wrong]  # вибір із двох
        self.rng.shuffle(options)
        return Question(
            SPELL, "word", w.id, "Оберіть правильне написання", prompt=w.ukrainian,
            choices=options, correct_choice=options.index(w.english), extra=extra,
        )

    def _quiz(self, w: Word, extra: str) -> Question | None:
        others = [x for x in self.words.values() if x.id != w.id]
        if self.rng.random() < 0.5:
            dist = self._pick_distractors([x.ukrainian for x in others], w.ukrainian)
            if not dist:
                return None
            return self._choice_question(QUIZ, "word", w.id, "Оберіть правильний переклад", w.english,
                                         w.ukrainian, dist, extra)
        dist = self._pick_distractors([x.english for x in others], w.english)
        if not dist:
            return None
        return self._choice_question(QUIZ, "word", w.id, "Оберіть правильне написання англійською", w.ukrainian,
                                     w.english, dist, extra)

    @staticmethod
    def _verb_extra(v: Verb) -> str:
        return f"{v.v1} — {v.v2} — {v.v3} ({v.translation})"

    def verb_question(self, v: Verb) -> Question:
        types = [VERB_FILL, VERB_TRANSLATE] + ([VERB_LISTEN] if self.audio else [])
        qtype = self.rng.choice(types)
        forms = (v.v1, v.v2, v.v3)
        extra = self._verb_extra(v)

        def form_field(i: int) -> Field:
            return Field(FORM_LABELS[i], form_variants(forms[i]), forms[i], "en")

        tr_field = Field("Переклад", translation_variants(v.translation), v.translation, "uk")

        if qtype == VERB_FILL:
            given = self.rng.randrange(3)
            return Question(
                qtype, "verb", v.id, "Впишіть дві інші форми дієслова",
                prompt=f"{FORM_LABELS[given]}: {forms[given]}", secondary=v.translation,
                fields=[form_field(i) for i in range(3) if i != given], extra=extra,
            )

        if qtype == VERB_TRANSLATE:
            line = " — ".join(forms)
            if self.rng.random() < 0.5:
                others = [x.translation for x in self.verbs.values() if x.id != v.id]
                dist = self._pick_distractors(others, v.translation)
                if dist:
                    return self._choice_question(VERB_TRANSLATE, "verb", v.id, "Оберіть переклад дієслова",
                                                 line, v.translation, dist, extra)
            return Question(qtype, "verb", v.id, "Введіть переклад дієслова", prompt=line,
                            fields=[tr_field], extra=extra)

        given = self.rng.randrange(3)
        if self.rng.random() < 0.5:
            return Question(
                qtype, "verb", v.id, "Прослухайте та впишіть дві інші форми",
                prompt=f"Звучить: {FORM_LABELS[given]}", audio=forms[given],
                fields=[form_field(i) for i in range(3) if i != given], extra=extra,
            )
        return Question(
            qtype, "verb", v.id, "Прослухайте та введіть переклад дієслова",
            prompt=f"Звучить: {FORM_LABELS[given]}", audio=forms[given], fields=[tr_field], extra=extra,
        )
