from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .verbs_data import IRREGULAR_VERBS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "english_trainer.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS words (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    english       TEXT NOT NULL,
    ukrainian     TEXT NOT NULL,
    example       TEXT NOT NULL DEFAULT '',
    transcription TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS irregular_verbs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    v1          TEXT NOT NULL,
    v2          TEXT NOT NULL,
    v3          TEXT NOT NULL,
    translation TEXT NOT NULL
);
-- Підсумкова статистика по кожному слову/дієслову
CREATE TABLE IF NOT EXISTS stats (
    kind      TEXT NOT NULL,            -- 'word' | 'verb'
    item_id   INTEGER NOT NULL,
    correct   INTEGER NOT NULL DEFAULT 0,
    wrong     INTEGER NOT NULL DEFAULT 0,
    streak    INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT,
    PRIMARY KEY (kind, item_id)
);
-- Повний журнал відповідей (основа для майбутніх інтервальних повторень)
CREATE TABLE IF NOT EXISTS answer_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    item_id     INTEGER NOT NULL,
    qtype       TEXT NOT NULL,
    correct     INTEGER NOT NULL,
    answered_at TEXT NOT NULL
);
-- Використані теми розмовної практики (щоб не повторювались)
CREATE TABLE IF NOT EXISTS topic_history (
    key     TEXT PRIMARY KEY,
    used_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS speaking_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    topic_key  TEXT NOT NULL,
    turns      INTEGER NOT NULL,
    issues     INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_usage (
    service TEXT NOT NULL,
    day     TEXT NOT NULL,
    calls   INTEGER NOT NULL DEFAULT 0,
    chars   INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (service, day)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass
class Word:
    id: int
    english: str
    ukrainian: str
    example: str = ""
    transcription: str = ""


@dataclass
class Verb:
    id: int
    v1: str
    v2: str
    v3: str
    translation: str


@dataclass
class Stat:
    correct: int = 0
    wrong: int = 0
    streak: int = 0
    last_seen: str | None = None

    @property
    def total(self) -> int:
        return self.correct + self.wrong

    @property
    def accuracy(self) -> int:
        return round(100 * self.correct / self.total) if self.total else 0


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str = DB_PATH):
        path = Path(path)
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._seed_verbs()
        self.conn.commit()

    def _seed_verbs(self) -> None:
        count = self.conn.execute("SELECT COUNT(*) FROM irregular_verbs").fetchone()[0]
        if count == 0:
            self.conn.executemany(
                "INSERT INTO irregular_verbs (v1, v2, v3, translation) VALUES (?, ?, ?, ?)",
                IRREGULAR_VERBS,
            )

    def add_word(self, english: str, ukrainian: str, transcription: str = "", example: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO words (english, ukrainian, example, transcription, created_at) VALUES (?, ?, ?, ?, ?)",
            (english.strip(), ukrainian.strip(), example.strip(), transcription.strip(), _now()),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def update_word(self, word_id: int, english: str, ukrainian: str, transcription: str, example: str) -> None:
        self.conn.execute(
            "UPDATE words SET english=?, ukrainian=?, example=?, transcription=? WHERE id=?",
            (english.strip(), ukrainian.strip(), example.strip(), transcription.strip(), word_id),
        )
        self.conn.commit()

    def delete_word(self, word_id: int) -> None:
        self.conn.execute("DELETE FROM words WHERE id=?", (word_id,))
        self.conn.execute("DELETE FROM stats WHERE kind='word' AND item_id=?", (word_id,))
        self.conn.execute("DELETE FROM answer_log WHERE kind='word' AND item_id=?", (word_id,))
        self.conn.commit()

    def word_exists(self, english: str, exclude_id: int | None = None) -> bool:
        target = english.strip().casefold()
        for row in self.conn.execute("SELECT id, english FROM words"):
            if row["id"] != exclude_id and row["english"].strip().casefold() == target:
                return True
        return False

    def get_words(self) -> list[Word]:
        rows = self.conn.execute(
            "SELECT id, english, ukrainian, example, transcription FROM words ORDER BY english COLLATE NOCASE"
        )
        return [Word(r["id"], r["english"], r["ukrainian"], r["example"], r["transcription"]) for r in rows]

    def get_verbs(self) -> list[Verb]:
        rows = self.conn.execute("SELECT id, v1, v2, v3, translation FROM irregular_verbs ORDER BY v1")
        return [Verb(r["id"], r["v1"], r["v2"], r["v3"], r["translation"]) for r in rows]

    def record_answer(self, kind: str, item_id: int, correct: bool, qtype: str = "") -> None:
        now = _now()
        self.conn.execute(
            """
            INSERT INTO stats (kind, item_id, correct, wrong, streak, last_seen)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(kind, item_id) DO UPDATE SET
                correct   = correct + excluded.correct,
                wrong     = wrong + excluded.wrong,
                streak    = CASE WHEN excluded.correct = 1 THEN streak + 1 ELSE 0 END,
                last_seen = excluded.last_seen
            """,
            (kind, item_id, int(correct), int(not correct), int(correct), now),
        )
        self.conn.execute(
            "INSERT INTO answer_log (kind, item_id, qtype, correct, answered_at) VALUES (?, ?, ?, ?, ?)",
            (kind, item_id, qtype, int(correct), now),
        )
        self.conn.commit()

    def get_stats(self, kind: str) -> dict[int, Stat]:
        rows = self.conn.execute(
            "SELECT item_id, correct, wrong, streak, last_seen FROM stats WHERE kind=?", (kind,)
        )
        return {r["item_id"]: Stat(r["correct"], r["wrong"], r["streak"], r["last_seen"]) for r in rows}

    def overall_stats(self) -> tuple[int, int]:
        row = self.conn.execute("SELECT COALESCE(SUM(correct),0), COALESCE(SUM(wrong),0) FROM stats").fetchone()
        return int(row[0]), int(row[1])

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.conn.commit()

    def used_topics(self) -> set[str]:
        return {r["key"] for r in self.conn.execute("SELECT key FROM topic_history")}

    def last_topic(self) -> str | None:
        row = self.conn.execute("SELECT key FROM topic_history ORDER BY used_at DESC, rowid DESC LIMIT 1").fetchone()
        return row["key"] if row else None

    def mark_topic_used(self, key: str) -> None:
        self.conn.execute(
            "INSERT INTO topic_history (key, used_at) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET used_at=excluded.used_at",
            (key, _now()),
        )
        self.conn.commit()

    def clear_used_topics(self, keys: list[str]) -> None:
        self.conn.executemany("DELETE FROM topic_history WHERE key=?", [(k,) for k in keys])
        self.conn.commit()

    def save_speaking_session(self, topic_key: str, turns: int, issues: int) -> None:
        self.conn.execute(
            "INSERT INTO speaking_sessions (topic_key, turns, issues, created_at) VALUES (?, ?, ?, ?)",
            (topic_key, turns, issues, _now()),
        )
        self.conn.commit()
