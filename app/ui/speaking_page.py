from __future__ import annotations

import html
from collections import Counter

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QPushButton, QTextBrowser, QVBoxLayout, QWidget,
)

from ..ai import (
    DEFAULT_LT_URL, DEFAULT_OLLAMA_URL, DEFAULT_TR_URL, RECOMMENDED_MODEL, Correction, LanguageToolClient,
    OllamaClient, Partner, TranslatorClient, choose_model,
)
from ..database import Database
from ..limits import languagetool_guard, translator_guard
from ..topics_data import CATEGORIES, LEVELS, Topic, pick_topic, remaining
from ..tts import Speaker


def service_error_note(err: str, what: str) -> str:
    if err.startswith("LIMIT:"):  # заблоковано локально ще до запиту
        return f"<i>{what} пропущено: {html.escape(err[6:].strip())}</i>"
    if "429" in err:
        return f"<i>{what}: перевищено ліміт безкоштовного сервісу. Спробуйте за хвилину (або завтра, якщо вичерпано денну квоту).</i>"
    return f"<i>{what} не виконано (немає інтернету чи сервер недоступний).</i>"


class TurnWorker(QThread):
    corrected = Signal(object, str)
    replied = Signal(str, bool)

    def __init__(self, partner: Partner, lt: LanguageToolClient | None, text: str):
        super().__init__()
        self.partner, self.lt, self.text = partner, lt, text

    def run(self) -> None:
        corr, err = None, ""
        if self.lt is not None:
            try:
                corr = self.lt.check(self.text)
            except Exception as exc:
                err = str(exc)
        self.corrected.emit(corr, err)
        try:
            reply = self.partner.reply(self.text)
        except Exception as exc:
            reply = "Sorry, something went wrong. Could you say that again?"
            err = str(exc)
        self.replied.emit(reply, self.partner.fell_back)


class TranslateWorker(QThread):
    done = Signal(str, str)

    def __init__(self, client: TranslatorClient, text: str):
        super().__init__()
        self.client, self.text = client, text

    def run(self) -> None:
        try:
            self.done.emit(self.client.translate(self.text), "")
        except Exception as exc:
            self.done.emit("", str(exc))


class SpeakingSettingsDialog(QDialog):
    def __init__(self, db: Database, parent: QWidget | None = None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Налаштування розмови")
        self.setMinimumWidth(520)
        form = QFormLayout(self)

        self.url = QLineEdit(db.get_setting("ollama_url", DEFAULT_OLLAMA_URL))
        form.addRow("Адреса Ollama:", self.url)

        row = QHBoxLayout()
        self.model = QComboBox()
        self.model.setEditable(True)
        refresh = QPushButton("Оновити")
        refresh.setObjectName("secondary")
        refresh.clicked.connect(self._refresh_models)
        row.addWidget(self.model, 1)
        row.addWidget(refresh)
        form.addRow("Модель:", row)
        self.info = QLabel("")
        self.info.setObjectName("muted")
        self.info.setWordWrap(True)
        form.addRow(self.info)

        self.use_lt = QCheckBox("Виправляти помилки через LanguageTool (онлайн)")
        self.use_lt.setChecked(db.get_setting("use_lt", "1") == "1")
        form.addRow(self.use_lt)
        self.lt_url = QLineEdit(db.get_setting("lt_url", DEFAULT_LT_URL))
        form.addRow("Адреса LanguageTool:", self.lt_url)
        usage = QLabel(translator_guard(db.path).usage_text())
        usage.setObjectName("muted")
        form.addRow(usage)
        note = QLabel("Ваші репліки надсилаються на сервер LanguageTool (перевірка граматики), а текст партнера — на MyMemory (кнопка «Переклад»).")
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Зберегти")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Скасувати")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self.model.setCurrentText(db.get_setting("ollama_model", ""))
        self._refresh_models()

    def _refresh_models(self) -> None:
        models = OllamaClient(self.url.text().strip()).models()
        current = self.model.currentText()
        self.model.clear()
        if models is None:
            self.info.setText("Ollama не знайдено — працюватиме керований режим (готові запитання за темою).\n"
                              f"Щоб увімкнути повний діалог: встановіть Ollama (ollama.com) і виконайте  "
                              f"ollama pull {RECOMMENDED_MODEL}")
        elif not models:
            self.info.setText(f"Ollama запущено, але моделей немає. Виконайте:  ollama pull {RECOMMENDED_MODEL}")
        else:
            self.model.addItems(models)
            current = current if current in models else (choose_model(models) or "")
            self.info.setText(f"Ollama працює. Знайдено моделей: {len(models)}.")
        self.model.setCurrentText(current)

    def _save(self) -> None:
        self.db.set_setting("ollama_url", self.url.text().strip() or DEFAULT_OLLAMA_URL)
        self.db.set_setting("ollama_model", self.model.currentText().strip())
        self.db.set_setting("use_lt", "1" if self.use_lt.isChecked() else "0")
        if self.use_lt.isChecked():
            self.db.set_setting("lt_consent", "1")  # свідоме ввімкнення = згода
        self.db.set_setting("lt_url", self.lt_url.text().strip() or DEFAULT_LT_URL)
        self.accept()


class SpeakingPage(QWidget):
    def __init__(self, db: Database, speaker: Speaker, parent: QWidget | None = None):
        super().__init__(parent)
        self.db, self.speaker = db, speaker
        self.topic: Topic | None = None
        self.partner: Partner | None = None
        self.turns = 0
        self.issue_log: list[tuple[str, str]] = []
        self.saved = True
        self.worker: TurnWorker | None = None
        self.tr_worker: TranslateWorker | None = None
        self.lt_guard = languagetool_guard()
        self.tr_guard = translator_guard(db.path)
        self.last_partner_text = ""
        self.model: str | None = None
        self.ollama_state = "off"

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 24)
        root.setSpacing(12)
        title = QLabel("Розмова")
        title.setObjectName("title")
        root.addWidget(title)

        bar = QHBoxLayout()
        self.cat = QComboBox()
        self.cat.addItem("Усі категорії", None)
        for c in CATEGORIES:
            self.cat.addItem(c, c)
        self.lvl = QComboBox()
        self.lvl.addItem("Будь-який рівень", None)
        for lv in LEVELS:
            self.lvl.addItem(lv, lv)
        self.cat.currentIndexChanged.connect(self._update_remaining)
        self.lvl.currentIndexChanged.connect(self._update_remaining)
        self.new_btn = QPushButton("🎲 Нова тема")
        self.new_btn.clicked.connect(self.new_topic)
        gear = QPushButton("⚙")
        gear.setObjectName("secondary")
        gear.setToolTip("Налаштування розмови")
        gear.clicked.connect(self.open_settings)
        bar.addWidget(self.cat)
        bar.addWidget(self.lvl)
        bar.addWidget(self.new_btn)
        bar.addStretch()
        bar.addWidget(gear)
        root.addLayout(bar)

        self.mode_label = QLabel("")
        self.mode_label.setObjectName("muted")
        root.addWidget(self.mode_label)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 12, 20, 12)
        self.topic_label = QLabel("Натисніть «Нова тема», щоб почати")
        self.topic_label.setObjectName("h2")
        self.remaining_label = QLabel("")
        self.remaining_label.setObjectName("muted")
        cl.addWidget(self.topic_label)
        cl.addWidget(self.remaining_label)
        root.addWidget(card)

        self.chat = QTextBrowser()
        root.addWidget(self.chat, 1)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setObjectName("answer")
        self.input.setPlaceholderText("Ваша відповідь англійською… (голосом: Win+H)")
        self.input.returnPressed.connect(self.send)
        self.send_btn = QPushButton("Надіслати")
        self.send_btn.clicked.connect(self.send)
        row.addWidget(self.input, 1)
        row.addWidget(self.send_btn)
        root.addLayout(row)

        foot = QHBoxLayout()
        self.audio_cb = QCheckBox("🔊 Озвучувати відповіді")
        self.audio_cb.setChecked(True)
        self.translate_btn = QPushButton("🇺🇦 Переклад")
        self.translate_btn.setObjectName("secondary")
        self.translate_btn.setToolTip("Перекласти останню репліку партнера")
        self.translate_btn.clicked.connect(self.translate_last)
        self.finish_btn = QPushButton("Завершити сесію")
        self.finish_btn.setObjectName("secondary")
        self.finish_btn.clicked.connect(self.finish_session)
        foot.addWidget(self.audio_cb)
        foot.addWidget(self.translate_btn)
        foot.addStretch()
        foot.addWidget(self.finish_btn)
        root.addLayout(foot)
        self._set_chat_enabled(False)

    def refresh(self) -> None:
        self._detect()
        self._update_remaining()
        self.audio_cb.setEnabled(self.speaker.is_available())

    def _detect(self) -> None:
        client = OllamaClient(self.db.get_setting("ollama_url", DEFAULT_OLLAMA_URL))
        models = client.models()
        if models is None:
            self.model, self.ollama_state = None, "off"
        elif not models:
            self.model, self.ollama_state = None, "nomodel"
        else:
            self.model, self.ollama_state = choose_model(models, self.db.get_setting("ollama_model", "")), "ready"
        brain = {
            "ready": f"🧠 Діалог: Ollama · {self.model}",
            "nomodel": f"💬 Керований режим (в Ollama немає моделей: ollama pull {RECOMMENDED_MODEL})",
            "off": "💬 Керований режим (Ollama не запущено — це нормально, усе працює)",
        }[self.ollama_state]
        lt = "✏ Виправлення: LanguageTool" if self.db.get_setting("use_lt", "1") == "1" else "✏ Виправлення вимкнено"
        self.mode_label.setText(f"{brain}   ·   {lt}")

    def _update_remaining(self) -> None:
        fresh, total = remaining(self.db, self.cat.currentData(), self.lvl.currentData())
        self.remaining_label.setText(
            f"Нових тем у вибраному наборі: {fresh} із {total}" if total else "У цьому наборі немає тем"
        )

    def open_settings(self) -> None:
        SpeakingSettingsDialog(self.db, self).exec()
        self._detect()

    def _set_chat_enabled(self, on: bool) -> None:
        self.input.setEnabled(on)
        self.send_btn.setEnabled(on)
        self.finish_btn.setEnabled(on)
        self.translate_btn.setEnabled(on)
        if on:
            self.input.setFocus()

    def _bubble(self, label: str, text: str, bg: str) -> None:
        self.chat.append(
            f'<table width="100%" cellspacing="0" cellpadding="8"><tr>'
            f'<td style="background-color:{bg}"><b>{label}</b><br>{html.escape(text)}</td></tr></table><br>'
        )

    def _note(self, markup: str) -> None:
        self.chat.append(f'<div style="color:#374151">{markup}</div><br>')

    def _ensure_consent(self) -> None:
        if (self.db.get_setting("use_lt", "1") != "1" or self.db.get_setting("lt_consent", "")
                or self.db.get_setting("lt_url", DEFAULT_LT_URL) != DEFAULT_LT_URL):
            return
        answer = QMessageBox.question(
            self, "Перевірка граматики",
            "Щоб виправляти помилки, ваші англійські репліки надсилатимуться на публічний сервер "
            "LanguageTool (api.languagetool.org). Особисті дані не передаються, лише текст реплік.\n\n"
            "Дозволити? Це можна змінити в ⚙.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        accepted = answer == QMessageBox.StandardButton.Yes
        self.db.set_setting("lt_consent", "1" if accepted else "0")
        if not accepted:
            self.db.set_setting("use_lt", "0")

    def new_topic(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self._ensure_consent()
        self._save_session()
        topic = pick_topic(self.db, self.cat.currentData(), self.lvl.currentData())
        if topic is None:
            QMessageBox.information(self, "Теми", "У вибраному наборі немає тем.")
            return
        self._detect()
        client = OllamaClient(self.db.get_setting("ollama_url", DEFAULT_OLLAMA_URL)) if self.model else None
        self.topic = topic
        self.partner = Partner(topic, self.lvl.currentData() or topic.level, client, self.model)
        self.turns, self.issue_log, self.saved = 0, [], False
        self.topic_label.setText(f"{topic.title}   ·   {topic.category} · {topic.level}")
        self._update_remaining()
        self.chat.clear()
        self._bubble("Партнер", topic.question, "#e0f2fe")
        self.last_partner_text = topic.question
        self._speak(topic.question)
        self._set_chat_enabled(True)

    def send(self) -> None:
        if not self.partner or (self.worker is not None and self.worker.isRunning()):
            return
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.turns += 1
        self._bubble("Ви", text, "#f3f4f6")
        self._set_chat_enabled(False)
        self.mode_label.setText("⏳ Співрозмовник відповідає…")
        lt = None
        if self.db.get_setting("use_lt", "1") == "1":
            url = self.db.get_setting("lt_url", DEFAULT_LT_URL)
            # власний (self-hosted) сервер не має публічних лімітів
            lt = LanguageToolClient(url, self.lt_guard if url == DEFAULT_LT_URL else None)
        self.worker = TurnWorker(self.partner, lt, text)
        self.worker.corrected.connect(self._on_corrected)
        self.worker.replied.connect(self._on_replied)
        self.worker.start()

    def _on_corrected(self, corr: Correction | None, err: str) -> None:
        if corr is None:
            if err:
                self._note(service_error_note(err, "Перевірку граматики"))
            return
        if not corr.issues:
            self._note("✅ Без помилок!")
            return
        lines = [f"✏ <b>Правильно:</b> {html.escape(corr.corrected)}"]
        for i in corr.issues:
            self.issue_log.append((i.wrong, i.suggestion))
            lines.append(f"• <b>{html.escape(i.wrong)}</b> → <b>{html.escape(i.suggestion)}</b>"
                         f" <span style='color:#6b7280'>— {html.escape(i.message)}</span>")
        self._note("<br>".join(lines))

    def _on_replied(self, text: str, fell_back: bool) -> None:
        self._bubble("Партнер", text, "#e0f2fe")
        self.last_partner_text = text
        self._speak(text)
        self._detect()
        if fell_back:
            self.mode_label.setText("💬 Модель не відповіла — перейшов у керований режим")
        self._set_chat_enabled(True)
        if self.partner is not None and self.partner.help_requested:
            self.translate_last()  # користувач не зрозумів — одразу даємо переклад

    def translate_last(self) -> None:
        if not self.last_partner_text or (self.tr_worker is not None and self.tr_worker.isRunning()):
            return
        self.translate_btn.setEnabled(False)
        url = self.db.get_setting("tr_url", DEFAULT_TR_URL)
        client = TranslatorClient(url, self.tr_guard if url == DEFAULT_TR_URL else None)
        self.tr_worker = TranslateWorker(client, self.last_partner_text)
        self.tr_worker.done.connect(self._on_translated)
        self.tr_worker.start()

    def _on_translated(self, text: str, err: str) -> None:
        self.translate_btn.setEnabled(self.partner is not None)
        if err:
            self._note(service_error_note(err, "Переклад"))
        else:
            self._note(f"🇺🇦 <i>{html.escape(text)}</i>")

    def _speak(self, text: str) -> None:
        if self.audio_cb.isChecked() and self.speaker.is_available():
            self.speaker.speak(text)

    def _save_session(self) -> None:
        if self.partner and self.topic and self.turns > 0 and not self.saved:
            self.db.save_speaking_session(self.topic.key, self.turns, len(self.issue_log))
        self.saved = True

    def finish_session(self) -> None:
        if not self.partner or (self.worker is not None and self.worker.isRunning()):
            return
        turns, issues = self.turns, self.issue_log
        self._save_session()
        parts = [f"<b>Підсумок сесії.</b> Ваших реплік: {turns}. Виправлень: {len(issues)}."]
        if issues:
            common = Counter(issues).most_common(5)
            parts.append("<b>Що варто повторити:</b><br>" + "<br>".join(
                f"• {html.escape(w)} → {html.escape(s)}" + (f" (×{n})" if n > 1 else "") for (w, s), n in common
            ))
        elif turns:
            parts.append("Жодної помилки — чудова робота! 🎉")
        self._note("<br>".join(parts))
        self.partner = None
        self._set_chat_enabled(False)
        self.topic_label.setText("Сесію завершено. Натисніть «Нова тема», щоб продовжити")
