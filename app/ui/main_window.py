from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QMainWindow, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from ..database import Database
from ..tts import ENGINES, Speaker
from .speaking_page import SpeakingPage
from .test_page import TestPage
from .verbs_page import VerbsPage
from .words_page import WordsPage


class HomePage(QWidget):
    navigate = Signal(int)

    CARDS = [
        ("📚", "Мій словник", "Додавайте власні слова, переклади та приклади", 1),
        ("📖", "Неправильні дієслова", "Таблиця всіх трьох форм із швидким пошуком", 2),
        ("📝", "Тестування", "Гнучкі тести зі слів та дієслів, 6 типів завдань", 3),
        ("🗣", "Розмова", "Практика мовлення на випадкові теми без повторів", 4),
    ]

    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        root = QVBoxLayout(self)
        root.setContentsMargins(48, 40, 48, 32)
        root.setSpacing(16)
        title = QLabel("English Trainer")
        title.setObjectName("title")
        sub = QLabel("Вивчайте англійські слова та неправильні дієслова")
        sub.setObjectName("muted")
        root.addWidget(title)
        root.addWidget(sub)
        root.addSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(16)
        for i, (icon, name, desc, page) in enumerate(self.CARDS):
            btn = QPushButton(f"{icon}   {name}\n\n{desc}")
            btn.setObjectName("cardBtn")
            btn.setMinimumHeight(130)
            btn.clicked.connect(lambda _=False, p=page: self.navigate.emit(p))
            grid.addWidget(btn, i // 2, i % 2)
        root.addLayout(grid)

        self.stats = QLabel("")
        self.stats.setObjectName("muted")
        root.addSpacing(8)
        root.addWidget(self.stats)
        root.addStretch()

    def refresh(self) -> None:
        words = len(self.db.get_words())
        verbs = len(self.db.get_verbs())
        ok, bad = self.db.overall_stats()
        total = ok + bad
        acc = f"{round(100 * ok / total)}%" if total else "—"
        self.stats.setText(
            f"Слів у словнику: {words}   ·   Неправильних дієслів: {verbs}   ·   "
            f"Відповідей дано: {total}   ·   Загальна точність: {acc}"
        )


class SettingsDialog(QDialog):
    def __init__(self, db: Database, speaker: Speaker, parent: QWidget | None = None):
        super().__init__(parent)
        self.db, self.speaker = db, speaker
        self.setWindowTitle("Налаштування")
        self.setMinimumWidth(440)
        form = QFormLayout(self)

        self.engine = QComboBox()
        for key, label in ENGINES.items():
            suffix = "" if Speaker.engine_available(key) else "  — не встановлено"
            self.engine.addItem(label + suffix, key)
        self.engine.setCurrentIndex(max(0, self.engine.findData(speaker.engine)))
        form.addRow("Рушій озвучки:", self.engine)

        test_btn = QPushButton("🔊 Перевірити озвучку")
        test_btn.setObjectName("secondary")
        test_btn.clicked.connect(self._test)
        form.addRow("", test_btn)
        hint = QLabel("gTTS потребує інтернету та пакета gTTS (pip install gTTS).\n"
                      "Якщо вибраний рушій недоступний, використовується інший.")
        hint.setObjectName("muted")
        form.addRow(hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Зберегти")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Скасувати")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _test(self) -> None:
        self.speaker.engine = self.engine.currentData()
        self.speaker.speak("Hello! This is a test of the speech engine.")

    def _save(self) -> None:
        key = self.engine.currentData()
        self.speaker.engine = key
        self.db.set_setting("tts_engine", key)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self, db: Database):
        super().__init__()
        self.db = db
        self.setWindowTitle("English Trainer")
        self.resize(1180, 780)

        self.speaker = Speaker(db.get_setting("tts_engine", "pyttsx3"))
        self.speaker.error.connect(lambda msg: self.statusBar().showMessage(msg, 9000))

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(280)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 22, 16, 16)
        sl.setSpacing(6)
        logo = QLabel("English Trainer")
        logo.setObjectName("logo")
        sl.addWidget(logo)
        sl.addSpacing(18)

        self.home = HomePage(db)
        self.words_page = WordsPage(db)
        self.verbs_page = VerbsPage(db, self.speaker)
        self.test_page = TestPage(db, self.speaker)
        self.speaking_page = SpeakingPage(db, self.speaker)
        self.pages = [self.home, self.words_page, self.verbs_page, self.test_page, self.speaking_page]

        self.stack = QStackedWidget()
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        labels = ["🏠   Головна", "📚   Мій словник", "📖   Неправильні дієслова", "📝   Тестування", "🗣   Розмова"]
        for i, text in enumerate(labels):
            btn = QPushButton(text)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            sl.addWidget(btn)
            self.nav.addButton(btn, i)
            self.stack.addWidget(self.pages[i])
        self.nav.idClicked.connect(self.show_page)
        sl.addStretch()

        settings_btn = QPushButton("⚙   Налаштування")
        settings_btn.setObjectName("nav")
        settings_btn.clicked.connect(self.open_settings)
        sl.addWidget(settings_btn)

        layout.addWidget(side)
        layout.addWidget(self.stack, 1)

        self.home.navigate.connect(self.go_to)
        self.go_to(0)

    def go_to(self, index: int) -> None:
        self.nav.button(index).setChecked(True)
        self.show_page(index)

    def show_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.pages[index].refresh()

    def open_settings(self) -> None:
        SettingsDialog(self.db, self.speaker, self).exec()
        self.test_page.refresh()
