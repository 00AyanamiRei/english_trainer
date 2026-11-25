from __future__ import annotations

import math
import sqlite3
import threading
import time
from collections import deque
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable


class LimitExceeded(Exception):
    def __init__(self, message: str, retry_after: float = 0.0, daily: bool = False):
        super().__init__(message)
        self.message, self.retry_after, self.daily = message, retry_after, daily

    def __str__(self) -> str:
        return f"LIMIT: {self.message}"


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seconds_to_utc_midnight() -> float:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (tomorrow - now).total_seconds()


class DailyBudget:
    def __init__(self, db_path: Path | str, service: str, max_chars: int, today: Callable[[], str] = _utc_today):
        self.db_path, self.service, self.max_chars, self._today = str(db_path), service, max_chars, today
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS api_usage (service TEXT NOT NULL, day TEXT NOT NULL, "
                "calls INTEGER NOT NULL DEFAULT 0, chars INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (service, day))"
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5)

    def used(self) -> int:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT chars FROM api_usage WHERE service=? AND day=?",
                               (self.service, self._today())).fetchone()
        return int(row[0]) if row else 0

    def check(self, chars: int) -> None:
        used = self.used()
        if used + chars > self.max_chars:
            raise LimitExceeded(
                f"денний ліміт {self.service} вичерпано ({used} із {self.max_chars} символів). "
                "Відновиться завтра (за UTC).",
                retry_after=_seconds_to_utc_midnight(), daily=True,
            )

    def commit(self, chars: int) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO api_usage (service, day, calls, chars) VALUES (?, ?, 1, ?) "
                "ON CONFLICT(service, day) DO UPDATE SET calls=calls+1, chars=chars+excluded.chars",
                (self.service, self._today(), chars),
            )

    def exhaust(self) -> None:
        with closing(self._connect()) as conn, conn:
            conn.execute(
                "INSERT INTO api_usage (service, day, calls, chars) VALUES (?, ?, 0, ?) "
                "ON CONFLICT(service, day) DO UPDATE SET chars=MAX(chars, excluded.chars)",
                (self.service, self._today(), self.max_chars),
            )


class ServiceGuard:
    def __init__(self, name: str, *, max_calls: int | None = None, window: float = 60.0,
                 max_chars_per_call: int | None = None, max_chars_per_window: int | None = None,
                 min_interval: float = 0.0, daily_chars: int | None = None, db_path: Path | str | None = None,
                 clock: Callable[[], float] = time.monotonic, today: Callable[[], str] = _utc_today):
        self.name, self.max_calls, self.window = name, max_calls, window
        self.max_chars_per_call, self.max_chars_per_window = max_chars_per_call, max_chars_per_window
        self.min_interval, self._clock = min_interval, clock
        self._calls: deque[tuple[float, int]] = deque()
        self._blocked_until = 0.0
        self._lock = threading.Lock()
        self.daily = DailyBudget(db_path, name, daily_chars, today) if daily_chars and db_path else None

    def acquire(self, chars: int) -> None:
        with self._lock:
            now = self._clock()
            while self._calls and now - self._calls[0][0] >= self.window:
                self._calls.popleft()

            if now < self._blocked_until:
                wait = self._blocked_until - now
                raise LimitExceeded(f"{self.name} тимчасово відхилив запити. Зачекайте {math.ceil(wait)} с.", wait)
            if self.max_chars_per_call is not None and chars > self.max_chars_per_call:
                raise LimitExceeded(f"текст задовгий для {self.name} ({chars} символів, максимум {self.max_chars_per_call}).")
            if self._calls and self.min_interval and now - self._calls[-1][0] < self.min_interval:
                wait = self.min_interval - (now - self._calls[-1][0])
                raise LimitExceeded(f"надто часті запити до {self.name}. Зачекайте {math.ceil(wait)} с.", wait)
            if self.max_calls is not None and len(self._calls) >= self.max_calls:
                wait = self.window - (now - self._calls[0][0])
                raise LimitExceeded(f"ліміт запитів до {self.name} ({self.max_calls}/хв). Зачекайте {math.ceil(wait)} с.", wait)
            if self.max_chars_per_window is not None and \
                    sum(c for _, c in self._calls) + chars > self.max_chars_per_window:
                wait = self.window - (now - self._calls[0][0]) if self._calls else 0.0
                raise LimitExceeded(f"ліміт обсягу тексту для {self.name}. Зачекайте {math.ceil(wait)} с.", wait)
            if self.daily is not None:
                self.daily.check(chars)

            self._calls.append((now, chars))
            if self.daily is not None:
                self.daily.commit(chars)

    def penalize(self, seconds: float = 60.0) -> None:
        with self._lock:
            self._blocked_until = max(self._blocked_until, self._clock() + seconds)

    def exhaust_today(self) -> None:
        if self.daily is not None:
            self.daily.exhaust()
        else:
            self.penalize(3600)

    def usage_text(self) -> str:
        return f"{self.name}: сьогодні {self.daily.used()} із {self.daily.max_chars} символів" if self.daily else ""

def languagetool_guard() -> ServiceGuard:
    return ServiceGuard("LanguageTool", max_calls=12, window=60, max_chars_per_call=5000,
                        max_chars_per_window=50000, min_interval=1.0)


def translator_guard(db_path: Path | str) -> ServiceGuard:
    return ServiceGuard("MyMemory", max_calls=10, window=60, max_chars_per_call=450, min_interval=1.0,
                        daily_chars=4500, db_path=db_path)


def gtts_guard() -> ServiceGuard:
    return ServiceGuard("gTTS", max_calls=20, window=60, max_chars_per_call=300, min_interval=0.5)
