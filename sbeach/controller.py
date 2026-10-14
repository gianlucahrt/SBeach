"""Ablaufsteuerung von SBeach, unabhängig von der Oberfläche.

Zustände: bereit, Aufnahme läuft, Transkription läuft (auch parallel zu einer
neuen Aufnahme). Die Oberfläche hängt sich über das UI Protokoll an, Zeitplanung
läuft über einen Scheduler, damit sich alles ohne macOS testen lässt.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import Callable, Protocol

from . import textproc

log = logging.getLogger(__name__)

SHOW_DELAY = 0.18    # Halten Modus: Overlay erst zeigen, wenn es kein Tastenkürzel war
CHORD_GRACE = 0.6    # Innerhalb dieser Zeit bricht eine Tastenkombination die Aufnahme ab
MIN_SECONDS = 0.3    # Kürzere Aufnahmen gelten als versehentliches Antippen


class UI(Protocol):
    def show_recording(self) -> None: ...
    def show_transcribing(self) -> None: ...
    def hide(self) -> None: ...
    def flash(self, message: str) -> None: ...
    def play(self, sound: str) -> None: ...
    def state_changed(self) -> None: ...


class Scheduler(Protocol):
    def call_after(self, fn: Callable, *args) -> None: ...
    def call_later(self, delay: float, fn: Callable, *args) -> None: ...


class Controller:
    def __init__(self, cfg, recorder, transcriber, ui: UI, scheduler: Scheduler,
                 deliver: Callable[[str], str], executor: Executor | None = None):
        """deliver(text) fügt den Text ein und gibt "inserted" oder "copied" zurück."""
        self.cfg = cfg
        self.recorder = recorder
        self.transcriber = transcriber
        self.ui = ui
        self.sched = scheduler
        self.deliver = deliver
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="sbeach-asr")
        self.recording = False
        self.revealed = False
        self.pending = 0
        self.session = 0
        self.history: deque[str] = deque(maxlen=int(cfg["history_size"]))
        self.status = "loading"          # loading | ready | error
        self.status_detail = ""
        self.last_language = ""
        self.last_duration = 0.0

    # Modell ---------------------------------------------------------------
    def preload(self) -> None:
        self.status = "loading"
        self.status_detail = ""
        self.ui.state_changed()
        fut = self.executor.submit(self.transcriber.load)
        fut.add_done_callback(lambda f: self.sched.call_after(self._loaded, f))

    def _loaded(self, fut) -> None:
        exc = fut.exception()
        if exc is not None:
            log.error("Modell konnte nicht geladen werden: %s", exc)
            self.status = "error"
            self.status_detail = str(exc)
        else:
            self.status = "ready"
            self.status_detail = ""
        self.ui.state_changed()

    # Eingaben -------------------------------------------------------------
    def on_hotkey(self, event: str) -> None:
        if event == "escape":
            if self.recording:
                self.cancel()
            return
        if self.cfg["mode"] == "hold":
            if event == "down" and not self.recording:
                self.start(SHOW_DELAY)
            elif event == "chord" and self.recording and self.recorder.elapsed() < CHORD_GRACE:
                self.cancel(silent=True)
            elif event in ("up", "up_chord") and self.recording:
                self.finish()
        else:  # toggle
            if event == "up":
                if self.recording:
                    self.finish()
                else:
                    self.start(0.0)

    def toggle(self) -> None:
        """Für Klick auf den Aufnahmeknopf."""
        if self.recording:
            self.finish()
        else:
            self.start(0.0)

    # Aufnahme -------------------------------------------------------------
    def start(self, show_delay: float = 0.0) -> None:
        if self.recording:
            return
        try:
            self.recorder.start()
        except Exception as exc:
            log.exception("Mikrofon konnte nicht gestartet werden")
            self.ui.flash("Mikrofon nicht verfügbar")
            self.status_detail = str(exc)
            return
        self.recording = True
        self.revealed = False
        self.session += 1
        if show_delay > 0:
            self.sched.call_later(show_delay, self._reveal, self.session)
        else:
            self._reveal(self.session)

    def _reveal(self, session: int) -> None:
        if not self.recording or session != self.session or self.revealed:
            return
        self.revealed = True
        if self.cfg["sounds"]:
            self.ui.play("start")
        self.ui.show_recording()
        self.ui.state_changed()

    def _after_recording(self) -> None:
        if self.pending:
            self.ui.show_transcribing()
        else:
            self.ui.hide()

    def cancel(self, silent: bool = False) -> None:
        if not self.recording:
            return
        self.recorder.cancel()
        self.recording = False
        was_visible, self.revealed = self.revealed, False
        self._after_recording()
        if was_visible and not silent and self.cfg["sounds"]:
            self.ui.play("cancel")
        self.ui.state_changed()

    def finish(self) -> None:
        if not self.recording:
            return
        duration = self.recorder.elapsed()
        audio = self.recorder.stop()
        self.recording = False
        was_visible, self.revealed = self.revealed, False
        if duration < MIN_SECONDS or textproc.is_silent(audio):
            self._after_recording()
            if was_visible and duration >= MIN_SECONDS and not self.pending:
                self.ui.flash("Nichts gehört")
            self.ui.state_changed()
            return
        if self.cfg["sounds"]:
            self.ui.play("stop")
        self.pending += 1
        self.ui.show_transcribing()
        self.ui.state_changed()
        quiet = textproc.is_quiet(audio)
        fut = self.executor.submit(self._transcribe, audio, quiet)
        fut.add_done_callback(lambda f: self.sched.call_after(self._done, f))

    # Erkennung ------------------------------------------------------------
    def _transcribe(self, audio, quiet: bool):
        started = time.monotonic()
        raw, lang = self.transcriber.transcribe(audio)
        text = textproc.clean(raw, quiet=quiet, trailing_space=self.cfg["trailing_space"])
        took = time.monotonic() - started
        log.info("Erkannt in %.2fs (%s, %.1fs Audio): %d Zeichen", took, lang,
                 audio.size / textproc.SAMPLE_RATE, len(text))
        return text, lang, took

    def _done(self, fut) -> None:
        self.pending = max(0, self.pending - 1)
        try:
            text, lang, took = fut.result()
        except Exception as exc:
            log.exception("Erkennung fehlgeschlagen")
            self.status = "error"
            self.status_detail = str(exc)
            if not self.recording:
                self.ui.flash("Erkennung fehlgeschlagen")
            self.ui.state_changed()
            return

        if self.status == "error":
            self.status = "ready"
        if not self.recording and not self.pending:
            self.ui.hide()

        if not text:
            if not self.recording:
                self.ui.flash("Nichts erkannt")
            self.ui.state_changed()
            return

        try:
            how = self.deliver(text)
        except Exception:
            log.exception("Text konnte nicht eingefügt werden")
            how = "failed"
        if how == "copied" and not self.recording:
            self.ui.flash("In die Zwischenablage kopiert")
        elif how == "failed" and not self.recording:
            self.ui.flash("Einfügen fehlgeschlagen")

        self.history.appendleft(text.strip())
        self.last_language = lang
        self.last_duration = took
        self.ui.state_changed()
