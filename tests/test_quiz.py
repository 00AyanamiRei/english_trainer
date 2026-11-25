import random

from app.quiz import (
    EN2UK, QUIZ, SPELL, VERB_FILL, Field, Question, QuestionGenerator, english_variants, evaluate,
    form_variants, mutate, normalize, translation_variants,
)


def test_normalize():
    assert normalize("  Hello,  World! ") == "hello, world"
    assert normalize("it’s") == "it's"


def test_variants():
    assert "кішка" in translation_variants("кіт, кішка")
    assert "were" in form_variants("was/were")
    assert "go" in english_variants("to go")
    assert "colour" in english_variants("colour (UK)")


def test_evaluate_text_accepts_any_variant_case_insensitive():
    q = Question(EN2UK, "word", 1, "x", fields=[Field("u", translation_variants("кіт, кішка"), "кіт, кішка", "uk")])
    assert evaluate(q, ["Кішка"]).correct
    assert evaluate(q, ["кіт, кішка"]).correct
    assert not evaluate(q, ["собака"]).correct


def test_evaluate_multi_field_requires_all():
    q = Question(VERB_FILL, "verb", 1, "x", fields=[
        Field("v2", form_variants("was/were"), "was/were"), Field("v3", form_variants("been"), "been")])
    assert evaluate(q, ["were", "been"]).correct
    ev = evaluate(q, ["were", "bean"])
    assert not ev.correct and ev.field_ok == [True, False]


def test_evaluate_choice():
    q = Question(QUIZ, "word", 1, "x", choices=["a", "b", "c"], correct_choice=1)
    assert evaluate(q, ["1"]).correct
    assert not evaluate(q, ["0"]).correct
    assert not evaluate(q, ["bad"]).correct


def test_mutate_always_changes_word():
    rng = random.Random(0)
    for word in ["cat", "a", "to run away", "house"]:
        for _ in range(50):
            assert normalize(mutate(word, rng)) != normalize(word)


def test_generator_covers_all_types_and_answers_are_consistent(populated_db):
    gen = QuestionGenerator(populated_db.get_words(), populated_db.get_verbs(), audio=True, rng=random.Random(1))
    seen = set()
    for kind, items in (("word", populated_db.get_words()), ("verb", populated_db.get_verbs())):
        for q in gen.build(kind, [i.id for i in items], 300):
            seen.add(q.qtype)
            if q.choices:
                assert len(set(q.choices)) == len(q.choices)
                assert evaluate(q, [str(q.correct_choice)]).correct
            else:
                assert evaluate(q, [f.display for f in q.fields]).correct
                assert not evaluate(q, ["zzz"] * len(q.fields)).correct
    assert len(seen) == 9


def test_no_audio_questions_when_audio_disabled(populated_db):
    gen = QuestionGenerator(populated_db.get_words(), populated_db.get_verbs(), audio=False, rng=random.Random(2))
    for kind, items in (("word", populated_db.get_words()), ("verb", populated_db.get_verbs())):
        assert all(not q.audio for q in gen.build(kind, [i.id for i in items], 200))


def test_quiz_skipped_without_distractors(db):
    wid = db.add_word("cat", "кіт")
    gen = QuestionGenerator(db.get_words(), [], audio=False, rng=random.Random(3))
    assert all(q.qtype != QUIZ for q in gen.build("word", [wid], 100))


def test_build_count_and_no_immediate_repeat(populated_db):
    ids = [w.id for w in populated_db.get_words()]
    gen = QuestionGenerator(populated_db.get_words(), [], audio=False, rng=random.Random(4))
    qs = gen.build("word", ids, 23)
    assert len(qs) == 23
    assert all(a.item_id != b.item_id for a, b in zip(qs, qs[1:]))
