from __future__ import annotations

from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..database import Database
from ..tts import Speaker


class VerbsPage(QWidget):
    COLUMNS = ["V1 — Infinitive", "V2 — Past Simple", "V3 — Past Participle", "Переклад"]
    SCOPES = ["Усі форми та переклад", "V1", "V2", "V3", "Переклад"]

    def __init__(self, db: Database, speaker: Speaker, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.speaker = speaker
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        title = QLabel("Неправильні дієслова")
        title.setObjectName("title")
        root.addWidget(title)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Швидкий пошук…")
        self.search.textChanged.connect(self.refresh)
        self.scope = QComboBox()
        self.scope.addItems(self.SCOPES)
        self.scope.currentIndexChanged.connect(self.refresh)
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        bar.addWidget(self.search, 1)
        bar.addWidget(self.scope)
        bar.addWidget(self.count_label)
        root.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _=None: self.speak_selected())
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        hint = QLabel("Подвійний клік або кнопка — озвучити всі три форми")
        hint.setObjectName("muted")
        actions.addWidget(hint)
        actions.addStretch()
        speak_btn = QPushButton("🔊 Озвучити")
        speak_btn.clicked.connect(self.speak_selected)
        actions.addWidget(speak_btn)
        root.addLayout(actions)

    def refresh(self) -> None:
        query = self.search.text().strip().casefold()
        scope = self.scope.currentIndex()
        rows = []
        verbs = self.db.get_verbs()
        for v in verbs:
            values = [v.v1, v.v2, v.v3, v.translation]
            haystack = " ".join(values) if scope == 0 else values[scope - 1]
            if query and query not in haystack.casefold():
                continue
            rows.append(values)

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, values in enumerate(rows):
            for c, text in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(text))
        self.table.setSortingEnabled(True)
        self.count_label.setText(f"Показано {len(rows)} із {len(verbs)}")

    def speak_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        forms = [self.table.item(row, c).text() for c in range(3)]
        self.speaker.speak(". ".join(forms))
