import pytest

from app.ai import AIError, LanguageToolClient, TranslatorClient
from app.limits import DailyBudget, LimitExceeded, ServiceGuard, languagetool_guard, translator_guard


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_sliding_window_blocks_then_recovers():
    clock = Clock()
    g = ServiceGuard("X", max_calls=3, window=60, clock=clock)
    for _ in range(3):
        g.acquire(10)
    with pytest.raises(LimitExceeded) as e:
        g.acquire(10)
    assert 0 < e.value.retry_after <= 60 and str(e.value).startswith("LIMIT:")
    clock.t += 61
    g.acquire(10)


def test_blocked_call_is_not_counted():
    clock = Clock()
    g = ServiceGuard("X", max_calls=1, window=60, clock=clock)
    g.acquire(1)
    for _ in range(5):
        with pytest.raises(LimitExceeded):
            g.acquire(1)
    clock.t += 61
    g.acquire(1)


def test_min_interval_and_per_call_and_per_window_chars():
    clock = Clock()
    g = ServiceGuard("X", min_interval=2, max_chars_per_call=100, max_chars_per_window=150, clock=clock)
    with pytest.raises(LimitExceeded, match="задовгий"):
        g.acquire(101)
    g.acquire(100)
    with pytest.raises(LimitExceeded, match="надто часті"):
        g.acquire(10)
    clock.t += 3
    with pytest.raises(LimitExceeded, match="обсягу"):
        g.acquire(60)
    g.acquire(50)


def test_penalize_blocks_until_pause_ends():
    clock = Clock()
    g = ServiceGuard("X", clock=clock)
    g.penalize(30)
    with pytest.raises(LimitExceeded, match="Зачекайте"):
        g.acquire(1)
    clock.t += 31
    g.acquire(1)


def test_daily_budget_persists_across_instances_and_resets_next_day(tmp_path):
    db, day = tmp_path / "u.db", ["2026-01-01"]
    g1 = ServiceGuard("M", daily_chars=100, db_path=db, today=lambda: day[0], clock=Clock())
    g1.acquire(60)
    g2 = ServiceGuard("M", daily_chars=100, db_path=db, today=lambda: day[0], clock=Clock())
    with pytest.raises(LimitExceeded) as e:
        g2.acquire(60)
    assert e.value.daily and "вичерпано" in e.value.message
    g2.acquire(40)  # рівно до межі
    with pytest.raises(LimitExceeded):
        g2.acquire(1)
    day[0] = "2026-01-02"
    g2.acquire(100)


def test_exhaust_blocks_rest_of_day(tmp_path):
    g = ServiceGuard("M", daily_chars=100, db_path=tmp_path / "u.db", clock=Clock())
    g.exhaust_today()
    with pytest.raises(LimitExceeded):
        g.acquire(1)
    assert DailyBudget(tmp_path / "u.db", "M", 100).used() == 100


def test_default_guards_are_below_published_limits(tmp_path):
    lt, tr = languagetool_guard(), translator_guard(tmp_path / "u.db")
    assert lt.max_calls < 20 and lt.max_chars_per_window < 75_000 and lt.max_chars_per_call < 20_000
    assert tr.daily.max_chars < 5000 and tr.max_chars_per_call <= 500


def test_languagetool_blocked_before_any_request(fake_server, server_hits):
    guard = ServiceGuard("LT", max_calls=1, window=60, clock=Clock())
    client = LanguageToolClient(f"{fake_server}/v2/check", guard)
    client.check("He go home")
    assert server_hits() == 1
    with pytest.raises(LimitExceeded):
        client.check("He go home")
    assert server_hits() == 1


def test_languagetool_429_pauses_further_requests(fake_server, server_hits):
    clock = Clock()
    client = LanguageToolClient(f"{fake_server}/limited", ServiceGuard("LT", clock=clock))
    with pytest.raises(AIError, match="429"):
        client.check("Hello there")
    assert server_hits() == 1
    with pytest.raises(LimitExceeded, match="тимчасово"):
        client.check("Hello there")
    assert server_hits() == 1
    clock.t += 61
    with pytest.raises(AIError, match="429"):
        client.check("Hello there")
    assert server_hits() == 2


def test_translator_daily_budget_blocks_before_request(fake_server, server_hits, tmp_path):
    guard = ServiceGuard("MyMemory", daily_chars=30, db_path=tmp_path / "u.db", clock=Clock())
    client = TranslatorClient(f"{fake_server}/get", guard)
    assert client.translate("Hello there!") == "Привіт"
    guard._clock = Clock()
    assert client.translate("Hello there!") == "Привіт"
    assert server_hits() == 2
    with pytest.raises(LimitExceeded, match="денний"):
        client.translate("Hello there!")
    assert server_hits() == 2


def test_translator_server_quota_blocks_until_tomorrow(fake_server, server_hits, tmp_path):
    guard = ServiceGuard("MyMemory", daily_chars=4500, db_path=tmp_path / "u.db", clock=Clock())
    client = TranslatorClient(f"{fake_server}/quota", guard)
    with pytest.raises(AIError, match="429"):
        client.translate("Hello")
    assert server_hits() == 1
    guard._clock = Clock()
    with pytest.raises(LimitExceeded, match="денний"):
        client.translate("Hello")
    assert server_hits() == 1
