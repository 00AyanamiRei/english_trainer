from __future__ import annotations

import html

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ..database import Database
from ..quiz import QTYPE_NAMES, Question, QuestionResult, evaluate
from ..tts import Speaker

_OK_BTN = ("QPushButton{background:#dcfce7;border:1px solid #16a34a;color:#14532d;text-align:left;"
           "padding:12px 16px;font-size:16px;font-weight:600;border-radius:6px;}")
_BAD_BTN = ("QPushButton{background:#fee2e2;border:1px solid #dc2626;color:#7f1d1d;text-align:left;"
            "padding:12px 16px;font-size:16px;font-weight:600;border-radius:6px;}")
_IDLE_BTN = ("QPushButton{background:white;border:1px solid #e5e7eb;color:#6b7280;text-align:left;"
             "padding:12px 16px;font-size:16px;border-radius:6px;}")
_OK_EDIT = "QLineEdit{border:1px solid #16a34a;background:#f0fdf4;border-radius:6px;padding:8px 10px;font-size:18px;}"
_BAD_EDIT = "QLineEdit{border:1px solid #dc2626;background:#fef2f2;border-radius:6px;padding:8px 10px;font-size:18px;}"


class TestSessionPage(QWidget):
    finished = Signal(list)  # list[QuestionResult]
    aborted = Signal()

    def __init__(self, db: Database, speaker: Speaker, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.speaker = speaker
        self.questions: list[Question] = []
        self.results: list[QuestionResult] = []
        self.index = 0
        self.answered = False
        self._inputs: list[QLineEdit] = []
        self._choice_buttons: list[QPushButton] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(48, 32, 48, 32)
        root.setSpacing(14)

        top = QHBoxLayout()
        self.progress_label = QLabel("")
        self.progress_label.setObjectName("h2")
        top.addWidget(self.progress_label)
        top.addStretch()
        quit_btn = QPushButton("Перервати тест")
        quit_btn.setObjectName("secondary")
        quit_btn.clicked.connect(self._on_quit)
        top.addWidget(quit_btn)
        root.addLayout(top)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        root.addWidget(self.progress)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(32, 26, 32, 26)
        cl.setSpacing(12)

        self.type_label = QLabel("")
        self.type_label.setObjectName("muted")
        self.instruction = QLabel("")
        self.instruction.setObjectName("h2")
        self.instruction.setWordWrap(True)
        self.prompt = QLabel("")
        self.prompt.setObjectName("prompt")
        self.prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.prompt.setWordWrap(True)
        self.second = QLabel("")
        self.second.setObjectName("second")
        self.second.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.second.setWordWrap(True)
        self.audio_btn = QPushButton("🔊 Прослухати ще раз")
        self.audio_btn.setObjectName("secondary")
        self.audio_btn.clicked.connect(self._play)

        cl.addWidget(self.type_label)
        cl.addWidget(self.instruction)
        cl.addSpacing(6)
        cl.addWidget(self.prompt)
        cl.addWidget(self.second)
        cl.addWidget(self.audio_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        cl.addSpacing(6)

        self.answer_area = QVBoxLayout()
        self.answer_area.setSpacing(8)
        cl.addLayout(self.answer_area)

        self.feedback = QLabel("")
        self.feedback.setWordWrap(True)
        self.feedback.setTextFormat(Qt.TextFormat.RichText)
        cl.addWidget(self.feedback)
        root.addWidget(card)

        bottom = QHBoxLayout()
        bottom.addStretch()
        self.primary = QPushButton("Перевірити")
        self.primary.setMinimumHeight(40)
        self.primary.setMinimumWidth(160)
        self.primary.clicked.connect(self._on_primary)
        bottom.addWidget(self.primary)
        root.addLayout(bottom)
        root.addStretch()

        for key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            sc = QShortcut(QKeySequence(key), self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(self._on_primary)

    # ------------------------------------------------------------------ flow
    def start(self, questions: list[Question]) -> None:
        self.questions = questions
        self.results = []
        self.index = 0
        self._show_question()

    def _clear_answer_area(self) -> None:
        while self.answer_area.count():
            item = self.answer_area.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._inputs = []
        self._choice_buttons = []

    def _show_question(self) -> None:
        q = self.questions[self.index]
        self.answered = False
        total = len(self.questions)
        self.progress_label.setText(f"Питання {self.index + 1} / {total}")
        self.progress.setMaximum(total)
        self.progress.setValue(self.index)

        self.type_label.setText(QTYPE_NAMES.get(q.qtype, ""))
        self.instruction.setText(q.instruction)
        self.prompt.setText(q.prompt)
        self.prompt.setVisible(bool(q.prompt))
        self.second.setText(q.secondary)
        self.second.setVisible(bool(q.secondary))
        self.audio_btn.setVisible(bool(q.audio))
        self.feedback.setText("")

        self._clear_answer_area()
        if q.choices:
            for i, text in enumerate(q.choices):
                btn = QPushButton(f"{i + 1}.  {text}")
                btn.setObjectName("choice")
                btn.clicked.connect(lambda _=False, idx=i: self._on_choice(idx))
                self.answer_area.addWidget(btn)
                self._choice_buttons.append(btn)
            self.primary.setVisible(False)
        else:
            for f in q.fields:
                label = QLabel(f.label)
                label.setObjectName("muted")
                edit = QLineEdit()
                edit.setObjectName("answer")
                edit.setPlaceholderText("Ваша відповідь…")
                self.answer_area.addWidget(label)
                self.answer_area.addWidget(edit)
                self._inputs.append(edit)
            self.primary.setText("Перевірити")
            self.primary.setVisible(True)
            if self._inputs:
                self._inputs[0].setFocus()

        if q.audio:
            QTimer.singleShot(300, self._play)

    def _play(self) -> None:
        if 0 <= self.index < len(self.questions) and self.questions[self.index].audio:
            self.speaker.speak(self.questions[self.index].audio)

    def _on_choice(self, idx: int) -> None:
        if self.answered:
            return
        q = self.questions[self.index]
        ev = evaluate(q, [str(idx)])
        for i, btn in enumerate(self._choice_buttons):
            if i == q.correct_choice:
                btn.setStyleSheet(_OK_BTN)
            elif i == idx:
                btn.setStyleSheet(_BAD_BTN)
            else:
                btn.setStyleSheet(_IDLE_BTN)
            btn.setEnabled(False)
        self._finish_question(ev)

    def _check_text(self) -> None:
        q = self.questions[self.index]
        answers = [e.text() for e in self._inputs]
        if not any(a.strip() for a in answers):
            self.feedback.setText('<span style="color:#b45309">Введіть відповідь.</span>')
            return
        ev = evaluate(q, answers)
        for edit, ok in zip(self._inputs, ev.field_ok):
            edit.setStyleSheet(_OK_EDIT if ok else _BAD_EDIT)
            edit.setReadOnly(True)
        self._finish_question(ev)

    def _finish_question(self, ev) -> None:
        q = self.questions[self.index]
        self.answered = True
        self.results.append(QuestionResult(q, ev))
        self.db.record_answer(q.kind, q.item_id, ev.correct, q.qtype)

        if ev.correct:
            text = '<span style="color:#15803d;font-weight:600">✅ Правильно!</span>'
        else:
            text = ('<span style="color:#b91c1c;font-weight:600">❌ Неправильно.</span><br>'
                    f'Правильна відповідь: <b>{html.escape(ev.correct_answer)}</b>')
        if q.extra:
            text += f'<br><span style="color:#6b7280">{html.escape(q.extra)}</span>'
        self.feedback.setText(text)

        last = self.index + 1 >= len(self.questions)
        self.primary.setText("Завершити" if last else "Далі →")
        self.primary.setVisible(True)
        self.progress.setValue(self.index + 1)

    def _on_primary(self) -> None:
        if not self.questions:
            return
        if not self.answered:
            if not self.questions[self.index].choices:
                self._check_text()
            return
        self.index += 1
        if self.index >= len(self.questions):
            self.finished.emit(self.results)
        else:
            self._show_question()

    def _on_quit(self) -> None:
        answer = QMessageBox.question(
            self, "Перервати тест", "Перервати тест? Уже дані відповіді буде збережено в статистиці.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if self.results:
            self.finished.emit(self.results)
        else:
            self.aborted.emit()
