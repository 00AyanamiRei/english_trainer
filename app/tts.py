from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal, Slot

from .limits import gtts_guard

ENGINES = {
    "pyttsx3": "pyttsx3 (офлайн)",
    "gtts": "gTTS (онлайн, краща вимова)",
}


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


class Speaker(QObject):
    error = Signal(str)
    _play_file = Signal(str)

    def __init__(self, engine: str = "pyttsx3", cache_dir: Path | str | None = None):
        super().__init__()
        self.engine = engine if engine in ENGINES else "pyttsx3"
        self.cache_dir = Path(cache_dir) if cache_dir else Path(__file__).resolve().parent.parent / "data" / "audio_cache"
        self._busy = threading.Lock()
        self._gtts_guard = gtts_guard()
        self._player = None
        self._audio = None
        self._play_file.connect(self._play_on_main)

    @staticmethod
    def engine_available(name: str) -> bool:
        if name == "pyttsx3":
            return _has("pyttsx3")
        if name == "gtts":
            return _has("gtts")
        return False

    def is_available(self) -> bool:
        return any(self.engine_available(n) for n in ENGINES)

    def speak(self, text: str) -> None:
        text = text.replace("/", ", ").strip()
        if text:
            threading.Thread(target=self._worker, args=(text,), daemon=True).start()

    def _worker(self, text: str) -> None:
        if not self._busy.acquire(blocking=False):
            return
        try:
            order = [self.engine] + [n for n in ENGINES if n != self.engine]
            errors: list[str] = []
            for name in order:
                if not self.engine_available(name):
                    continue
                try:
                    (self._say_gtts if name == "gtts" else self._say_pyttsx3)(text)
                    return
                except Exception as exc:
                    errors.append(f"{ENGINES[name]}: {exc}")
            if errors:
                self.error.emit("Не вдалося відтворити звук. " + "; ".join(errors))
            else:
                self.error.emit("Немає TTS-рушія. Встановіть: pip install pyttsx3 (або gTTS).")
        finally:
            self._busy.release()

    def _say_pyttsx3(self, text: str) -> None:
        com = None
        if sys.platform == "win32":
            try:
                import comtypes

                comtypes.CoInitialize()
                com = comtypes
            except Exception:
                com = None
        try:
            import pyttsx3

            engine = pyttsx3.init()
            engine.setProperty("rate", 150)
            for voice in engine.getProperty("voices") or []:
                blob = f"{voice.id} {voice.name} {voice.languages}".casefold()
                if "english" in blob or "en-" in blob or "en_" in blob or "en-us" in blob:
                    engine.setProperty("voice", voice.id)
                    break
            engine.say(text)
            engine.runAndWait()
            engine.stop()
            del engine
        finally:
            if com is not None:
                try:
                    com.CoUninitialize()
                except Exception:  # noqa: BLE001
                    pass

    @Slot(str)
    def _play_on_main(self, path: str) -> None:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        if self._player is None:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.errorOccurred.connect(lambda _err, msg: self.error.emit(f"Відтворення mp3: {msg}"))
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))
        self._player.play()

    def _say_gtts(self, text: str) -> None:
        from gtts import gTTS

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self.cache_dir / f"{hashlib.md5(text.encode('utf-8')).hexdigest()}.mp3"
        if not path.exists():
            self._gtts_guard.acquire(len(text))
            gTTS(text=text, lang="en").save(str(path))
        self._play_file.emit(str(path))
