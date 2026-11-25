from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from ..database import Database, Stat, Word


class WordDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, word: Word | None = None):
        super().__init__(parent)
        self.setWindowTitle("Редагувати слово" if word else "Нове слово")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        self.english = QLineEdit(word.english if word else "")
        self.ukrainian = QLineEdit(word.ukrainian if word else "")
        self.transcription = QLineEdit(word.transcription if word else "")
        self.example = QLineEdit(word.example if word else "")
        form.addRow("Англійською:", self.english)
        form.addRow("Переклад:", self.ukrainian)
        form.addRow("Транскрипція:", self.transcription)
        form.addRow("Приклад:", self.example)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Зберегти")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Скасувати")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _accept(self) -> None:
        if not self.english.text().strip() or not self.ukrainian.text().strip():
            QMessageBox.warning(self, "Порожнє поле", "Англійське слово і переклад є обов'язковими.")
            return
        self.accept()

    def values(self) -> tuple[str, str, str, str]:
        return (
            self.english.text().strip(), self.ukrainian.text().strip(),
            self.transcription.text().strip(), self.example.text().strip(),
        )


class WordsPage(QWidget):
    COLUMNS = ["Англійською", "Переклад", "Транскрипція", "Приклад", "Успішність"]

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(14)

        title = QLabel("Мій словник")
        title.setObjectName("title")
        root.addWidget(title)

        # --- форма додавання
        box = QGroupBox("Додати слово або фразу")
        grid = QHBoxLayout(box)
        self.in_en = QLineEdit()
        self.in_en.setPlaceholderText("English word / phrase *")
        self.in_uk = QLineEdit()
        self.in_uk.setPlaceholderText("Український переклад *")
        self.in_tr = QLineEdit()
        self.in_tr.setPlaceholderText("Транскрипція (необов'язково)")
        self.in_ex = QLineEdit()
        self.in_ex.setPlaceholderText("Приклад використання (необов'язково)")
        for w in (self.in_en, self.in_uk, self.in_tr, self.in_ex):
            w.returnPressed.connect(self.add_word)
            grid.addWidget(w, 1)
        add_btn = QPushButton("＋ Додати")
        add_btn.clicked.connect(self.add_word)
        grid.addWidget(add_btn)
        root.addWidget(box)

        self.status = QLabel("")
        self.status.setObjectName("muted")
        root.addWidget(self.status)

        # --- пошук і фільтр
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Пошук за словом, перекладом, прикладом…")
        self.search.textChanged.connect(self.refresh)
        self.filter = QComboBox()
        self.filter.addItems(["Усі слова", "З помилками", "Нові (ще без тестів)"])
        self.filter.currentIndexChanged.connect(self.refresh)
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        bar.addWidget(self.search, 1)
        bar.addWidget(self.filter)
        bar.addWidget(self.count_label)
        root.addLayout(bar)

        # --- таблиця
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.doubleClicked.connect(lambda _=None: self.edit_selected())
        root.addWidget(self.table, 1)

        actions = QHBoxLayout()
        actions.addStretch()
        edit_btn = QPushButton("✏ Редагувати")
        edit_btn.setObjectName("secondary")
        edit_btn.clicked.connect(self.edit_selected)
        del_btn = QPushButton("🗑 Видалити")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self.delete_selected)
        actions.addWidget(edit_btn)
        actions.addWidget(del_btn)
        root.addLayout(actions)

    # ------------------------------------------------------------------
    def refresh(self) -> None:
        stats = self.db.get_stats("word")
        query = self.search.text().strip().casefold()
        mode = self.filter.currentIndex()
        rows: list[tuple[Word, Stat]] = []
        total = 0
        for w in self.db.get_words():
            total += 1
            st = stats.get(w.id, Stat())
            blob = f"{w.english} {w.ukrainian} {w.transcription} {w.example}".casefold()
            if query and query not in blob:
                continue
            if mode == 1 and st.wrong == 0:
                continue
            if mode == 2 and st.total > 0:
                continue
            rows.append((w, st))

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for r, (w, st) in enumerate(rows):
            acc = f"{st.accuracy}% ({st.correct}/{st.total})" if st.total else "—"
            for c, text in enumerate([w.english, w.ukrainian, w.transcription, w.example, acc]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, w.id)
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self.count_label.setText(f"Показано {len(rows)} із {total}")

    def _selected_id(self) -> int | None:
        row = self.table.currentRow()
        if row < 0 or self.table.item(row, 0) is None:
            return None
        return int(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))

    def add_word(self) -> None:
        en, uk = self.in_en.text().strip(), self.in_uk.text().strip()
        if not en or not uk:
            self.status.setText("⚠ Заповніть англійське слово та переклад.")
            return
        if self.db.word_exists(en):
            self.status.setText(f"⚠ Слово «{en}» уже є у словнику.")
            return
        self.db.add_word(en, uk, self.in_tr.text(), self.in_ex.text())
        for w in (self.in_en, self.in_uk, self.in_tr, self.in_ex):
            w.clear()
        self.in_en.setFocus()
        self.status.setText(f"✅ Додано: {en} — {uk}")
        self.refresh()

    def edit_selected(self) -> None:
        word_id = self._selected_id()
        if word_id is None:
            QMessageBox.information(self, "Редагування", "Спочатку виберіть слово в таблиці.")
            return
        word = next((w for w in self.db.get_words() if w.id == word_id), None)
        if word is None:
            return
        dlg = WordDialog(self, word)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            en, uk, tr, ex = dlg.values()
            if self.db.word_exists(en, exclude_id=word_id):
                QMessageBox.warning(self, "Дублікат", f"Слово «{en}» уже є у словнику.")
                return
            self.db.update_word(word_id, en, uk, tr, ex)
            self.refresh()

    def delete_selected(self) -> None:
        word_id = self._selected_id()
        if word_id is None:
            QMessageBox.information(self, "Видалення", "Спочатку виберіть слово в таблиці.")
            return
        row = self.table.currentRow()
        name = self.table.item(row, 0).text()
        answer = QMessageBox.question(
            self, "Видалити слово", f"Видалити «{name}» разом зі статистикою?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.db.delete_word(word_id)
            self.refresh()
