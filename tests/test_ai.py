import random

import pytest

from app.ai import (
    AIError, LanguageToolClient, OllamaClient, Partner, TranslatorClient, choose_model, fit_bytes, is_help_request,
)
from app.topics_data import TOPICS


def test_languagetool_applies_corrections_and_skips_typography(fake_server):
    corr = LanguageToolClient(f"{fake_server}/v2/check").check("He go home")
    assert corr.corrected == "He goes home"
    assert [(i.wrong, i.suggestion) for i in corr.issues] == [("go", "goes")]


def test_ollama_models_and_chat(fake_server):
    client = OllamaClient(fake_server)
    assert choose_model(client.models()) == "qwen2.5:1.5b"
    assert "Great" in client.chat("m", [{"role": "user", "content": "hi"}])


def test_ollama_not_running_returns_none():
    assert OllamaClient("http://127.0.0.1:9").models() is None


def test_translator(fake_server):
    assert TranslatorClient(f"{fake_server}/get").translate("Hello") == "Привіт"


def test_choose_model_prefers_small_known_models():
    assert choose_model(["mistral:7b", "llama3.2:1b"]) == "llama3.2:1b"
    assert choose_model(["a", "b"], saved="b") == "b"
    assert choose_model([]) is None


def test_help_intent():
    for text in ["I don't understand it's question. Translate please.", "what do you mean?", "Не розумію", "repeat please"]:
        assert is_help_request(text)
    for text in ["I like swimming in the sea with my family", "Yes, I do"]:
        assert not is_help_request(text)


def test_guided_partner_repeats_question_on_help_and_nudges_short_answers():
    p = Partner(TOPICS[0], "A2", rng=random.Random(1))
    assert TOPICS[0].question in p.reply("I don't understand")
    assert p.help_requested
    assert "more" in p.reply("yes").lower()
    follow = p.reply("I usually wake up at seven and drink coffee")
    assert not p.help_requested and follow.endswith("?")
    assert follow in p.reply("Не розумію")


def test_partner_uses_ollama_and_falls_back_when_it_dies(fake_server):
    p = Partner(TOPICS[0], "B1", OllamaClient(fake_server), "m", random.Random(1))
    assert p.reply("I like the sea very much") == "Great! What do you like most about it?"
    dead = Partner(TOPICS[0], "B1", OllamaClient("http://127.0.0.1:9"), "m", random.Random(1))
    assert dead.reply("I like the sea very much") and dead.fell_back


def test_http_429_is_reported_as_rate_limit(fake_server):
    with pytest.raises(AIError, match="429"):
        TranslatorClient(f"{fake_server}/limited").translate("Hello")
    with pytest.raises(AIError, match="429"):
        TranslatorClient(f"{fake_server}/quota").translate("Hello")


def test_fit_bytes_respects_mymemory_limit_and_cuts_on_sentence():
    text = "This is a sentence. " * 60
    out = fit_bytes(text)
    assert len(out.encode()) <= 450 and out.endswith(".")
    assert fit_bytes("Short.") == "Short."
    assert len(fit_bytes("я" * 400).encode()) <= 450
