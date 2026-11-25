from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QRadioButton, QSpinBox, QVBoxLayout, QWidget,
)

from ..database import Database
from ..tts import Speaker


class TestSetupPage(QWidget):
    # kind, ids, count, audio_enabled
    start_requested = Signal(str, list, int, bool)

    def __init__(self, db: Database, speaker: Speaker, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.speaker = speaker
        self._loaded_kind: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(12)

        title = QLabel("Тестування")
        title.setObjectName("title")
        root.addWidget(title)
        sub = QLabel("Виберіть, що вчити, позначте слова й налаштуйте сесію")
        sub.setObjectName("muted")
        root.addWidget(sub)

        # --- джерело
        src = QHBoxLayout()
        src.addWidget(QLabel("Джерело:"))
        self.rb_words = QRadioButton("Мій словник")
        self.rb_verbs = QRadioButton("Неправильні дієслова")
        self.rb_words.setChecked(True)
        group = QButtonGroup(self)
        group.addButton(self.rb_words)
        group.addButton(self.rb_verbs)
        self.rb_words.toggled.connect(lambda _=None: self._load(reset=True))
        src.addWidget(self.rb_words)
        src.addWidget(self.rb_verbs)
        src.addStretch()
        root.addLayout(src)

        # --- пошук + масові дії
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 Фільтр списку…")
        self.search.textChanged.connect(self._apply_filter)
        btn_all = QPushButton("Вибрати всі")
        btn_all.setObjectName("secondary")
        btn_all.clicked.connect(self._select_all)
        btn_none = QPushButton("Зняти вибір")
        btn_none.setObjectName("secondary")
        btn_none.clicked.connect(self._clear_all)
        bar.addWidget(self.search, 1)
        bar.addWidget(btn_all)
        bar.addWidget(btn_none)
        root.addLayout(bar)

        self.list = QListWidget()
        self.list.setAlternatingRowColors(True)
        self.list.itemChanged.connect(lambda _=None: self._update_count())
        root.addWidget(self.list, 1)

        self.hint = QLabel("")
        self.hint.setObjectName("muted")
        root.addWidget(self.hint)

        # --- налаштування
        opts = QHBoxLayout()
        self.selected_label = QLabel("Вибрано: 0")
        self.selected_label.setObjectName("h2")
        self.auto_count = QCheckBox("Кількість питань = кількість вибраних")
        self.auto_count.setChecked(True)
        self.auto_count.toggled.connect(lambda _=None: self._update_count())
        self.spin = QSpinBox()
        self.spin.setRange(1, 500)
        self.spin.setValue(10)
        self.spin.setSuffix(" питань")
        self.audio_cb = QCheckBox("Питання на слух")
        opts.addWidget(self.selected_label)
        opts.addStretch()
        opts.addWidget(self.auto_count)
        opts.addWidget(self.spin)
        opts.addWidget(self.audio_cb)
        root.addLayout(opts)

        run = QHBoxLayout()
        run.addStretch()
        self.start_btn = QPushButton("▶ Почати тест")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self._start)
        run.addWidget(self.start_btn)
        root.addLayout(run)

    # ------------------------------------------------------------------
    @property
    def kind(self) -> str:
        return "word" if self.rb_words.isChecked() else "verb"

    def refresh(self) -> None:
        available = self.speaker.is_available()
        self.audio_cb.setEnabled(available)
        if not available:
            self.audio_cb.setChecked(False)
            self.audio_cb.setToolTip("Встановіть pyttsx3 (або gTTS), щоб увімкнути аудіювання")
        elif not self.audio_cb.isEnabled() or self._loaded_kind is None:
            self.audio_cb.setChecked(True)
        self._load(reset=False)

    def _checked_ids(self) -> set[int]:
        ids = set()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                ids.add(int(item.data(Qt.ItemDataRole.UserRole)))
        return ids

    def _load(self, reset: bool) -> None:
        kind = self.kind
        keep = set() if (reset or kind != self._loaded_kind) else self._checked_ids()
        self.list.blockSignals(True)
        self.list.clear()
        if kind == "word":
            entries = [(w.id, f"{w.english} — {w.ukrainian}") for w in self.db.get_words()]
            self.hint.setText("" if entries else "Словник порожній — додайте слова в розділі «Мій словник».")
        else:
            entries = [(v.id, f"{v.v1} — {v.v2} — {v.v3}   ({v.translation})") for v in self.db.get_verbs()]
            self.hint.setText("")
        for item_id, text in entries:
            item = QListWidgetItem(text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if item_id in keep else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, item_id)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._loaded_kind = kind
        self._apply_filter()
        self._update_count()

    def _apply_filter(self) -> None:
        query = self.search.text().strip().casefold()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(query) and query not in item.text().casefold())

    def _set_all(self, state: Qt.CheckState, visible_only: bool) -> None:
        self.list.blockSignals(True)
        for i in range(self.list.count()):
            item = self.list.item(i)
            if visible_only and item.isHidden():
                continue
            item.setCheckState(state)
        self.list.blockSignals(False)
        self._update_count()

    def _select_all(self) -> None:
        self._set_all(Qt.CheckState.Checked, visible_only=True)

    def _clear_all(self) -> None:
        self._set_all(Qt.CheckState.Unchecked, visible_only=False)

    def _update_count(self) -> None:
        n = len(self._checked_ids())
        self.selected_label.setText(f"Вибрано: {n}")
        if self.auto_count.isChecked():
            self.spin.setValue(max(1, n))
        self.spin.setEnabled(not self.auto_count.isChecked())
        self.start_btn.setEnabled(n > 0)

    def _start(self) -> None:
        ids = sorted(self._checked_ids())
        if not ids:
            return
        self.start_requested.emit(self.kind, ids, self.spin.value(), self.audio_cb.isChecked())
