from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..database import Database
from ..quiz import QTYPE_NAMES, QuestionGenerator, QuestionResult
from ..tts import Speaker
from .test_session_page import TestSessionPage
from .test_setup_page import TestSetupPage


class ResultsPage(QWidget):
    retry = Signal()
    retry_mistakes = Signal()
    back = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._mistakes: list[tuple[str, int]] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        title = QLabel("Підсумки тесту")
        title.setObjectName("title")
        root.addWidget(title)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 20, 28, 20)
        self.score = QLabel("")
        self.score.setObjectName("prompt")
        self.details = QLabel("")
        self.details.setObjectName("h2")
        cl.addWidget(self.score)
        cl.addWidget(self.details)
        root.addWidget(card)

        self.errors_title = QLabel("Розбір помилок")
        self.errors_title.setObjectName("h2")
        root.addWidget(self.errors_title)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Тип", "Завдання", "Ваша відповідь", "Правильна відповідь"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        root.addWidget(self.table, 1)

        self.perfect = QLabel("🎉 Жодної помилки — чудова робота!")
        self.perfect.setObjectName("h2")
        self.perfect.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.perfect)

        row = QHBoxLayout()
        back = QPushButton("← До налаштувань")
        back.setObjectName("secondary")
        back.clicked.connect(self.back.emit)
        self.btn_mistakes = QPushButton("Повторити помилки")
        self.btn_mistakes.setObjectName("secondary")
        self.btn_mistakes.clicked.connect(self.retry_mistakes.emit)
        again = QPushButton("↻ Пройти ще раз")
        again.clicked.connect(self.retry.emit)
        row.addWidget(back)
        row.addStretch()
        row.addWidget(self.btn_mistakes)
        row.addWidget(again)
        root.addLayout(row)

    def show_results(self, results: list[QuestionResult]) -> None:
        total = len(results)
        ok = sum(1 for r in results if r.evaluation.correct)
        bad = total - ok
        pct = round(100 * ok / total) if total else 0
        self.score.setText(f"{ok} / {total}  ({pct}%)")
        self.details.setText(f"✅ Правильно: {ok}      ❌ Неправильно: {bad}")

        wrong = [r for r in results if not r.evaluation.correct]
        self._mistakes = [(r.question.kind, r.question.item_id) for r in wrong]
        self.table.setRowCount(len(wrong))
        for i, r in enumerate(wrong):
            q = r.question
            values = [
                QTYPE_NAMES.get(q.qtype, ""), q.describe(),
                r.evaluation.user_answer or "—", r.evaluation.correct_answer,
            ]
            for c, text in enumerate(values):
                self.table.setItem(i, c, QTableWidgetItem(text))
        self.table.resizeRowsToContents()
        has_errors = bool(wrong)
        self.errors_title.setVisible(has_errors)
        self.table.setVisible(has_errors)
        self.btn_mistakes.setVisible(has_errors)
        self.perfect.setVisible(not has_errors)

    def mistake_ids(self) -> tuple[str, list[int]] | None:
        if not self._mistakes:
            return None
        kind = self._mistakes[0][0]
        ids = list(dict.fromkeys(i for k, i in self._mistakes if k == kind))
        return kind, ids


class TestPage(QWidget):
    def __init__(self, db: Database, speaker: Speaker, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.speaker = speaker
        self._config: tuple[str, list[int], int, bool] | None = None

        self.setup = TestSetupPage(db, speaker)
        self.session = TestSessionPage(db, speaker)
        self.results = ResultsPage()
        self.stack = QStackedWidget()
        for page in (self.setup, self.session, self.results):
            self.stack.addWidget(page)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        self.setup.start_requested.connect(self._on_start)
        self.session.finished.connect(self._on_finished)
        self.session.aborted.connect(self._to_setup)
        self.results.back.connect(self._to_setup)
        self.results.retry.connect(self._on_retry)
        self.results.retry_mistakes.connect(self._on_retry_mistakes)

    def refresh(self) -> None:
        if self.stack.currentWidget() is self.setup:
            self.setup.refresh()

    def _to_setup(self) -> None:
        self.stack.setCurrentWidget(self.setup)
        self.setup.refresh()

    def _on_start(self, kind: str, ids: list, count: int, audio: bool) -> None:
        self._config = (kind, ids, count, audio)
        self._run(kind, ids, count, audio)

    def _run(self, kind: str, ids: list[int], count: int, audio: bool) -> None:
        gen = QuestionGenerator(self.db.get_words(), self.db.get_verbs(), audio=audio and self.speaker.is_available())
        questions = gen.build(kind, ids, count)
        self.session.start(questions)
        self.stack.setCurrentWidget(self.session)

    def _on_finished(self, results: list) -> None:
        self.results.show_results(results)
        self.stack.setCurrentWidget(self.results)

    def _on_retry(self) -> None:
        if self._config:
            self._run(*self._config)

    def _on_retry_mistakes(self) -> None:
        info = self.results.mistake_ids()
        if info and self._config:
            kind, ids = info
            self._run(kind, ids, len(ids), self._config[3])
