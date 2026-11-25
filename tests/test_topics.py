import random

from app.topics_data import CATEGORIES, LEVELS, TOPICS, pick_topic, remaining


def test_topic_catalog_is_consistent():
    assert len(TOPICS) >= 80
    assert len({t.key for t in TOPICS}) == len(TOPICS)
    assert all(t.level in LEVELS and t.category in CATEGORIES and t.question.endswith(("?", ".")) for t in TOPICS)


def test_no_repeats_until_pool_exhausted(db):
    rng = random.Random(1)
    keys = [pick_topic(db, rng=rng).key for _ in range(len(TOPICS))]
    assert len(set(keys)) == len(TOPICS)
    assert remaining(db, None, None) == (0, len(TOPICS))


def test_reset_does_not_start_with_last_topic(db):
    rng = random.Random(2)
    last = [pick_topic(db, rng=rng).key for _ in range(len(TOPICS))][-1]
    assert pick_topic(db, rng=rng).key != last


def test_filters(db):
    rng = random.Random(3)
    for _ in range(10):
        t = pick_topic(db, "Подорожі", "B1", rng)
        assert t.category == "Подорожі" and t.level == "B1"
    assert pick_topic(db, "Немає такої", None) is None
