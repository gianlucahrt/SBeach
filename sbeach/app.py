"""Startpunkt: verbindet Kernlogik und Oberfläche zu einer macOS Menüleisten App."""

from __future__ import annotations

import logging
import logging.handlers
import sys

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSPasteboard,
    NSPasteboardTypeString,
    NSSound,
    NSWorkspace,
)
from Foundation import NSURL, NSBundle, NSObject, NSTimer, NSUserDefaults
from PyObjCTools import AppHelper

from . import APP_NAME, __version__, inserter
from .audio import Recorder, input_devices
from .config import Config, log_path
from .controller import Controller
from .hotkey import HOTKEYS, HotkeyTap
from .transcriber import MODELS, Transcriber
from . import llm, media
from .ui.hud import Hud
from .ui.main_window import MainWindow
from .ui.menubar import StatusMenu
from .ui.result_window import ResultWindow
from .ui.settings import SettingsWindow

log = logging.getLogger("sbeach")

PRIVACY = "x-apple.systempreferences:com.apple.preference.security?"
LANG_SHORT = {"auto": "DE / EN", "de": "Deutsch", "en": "Englisch"}
SOUNDS = {"start": ("Pop", 0.22), "stop": ("Tink", 0.22), "cancel": ("Pop", 0.10)}


def setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=2,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None and sys.stderr.isatty():
        root.addHandler(logging.StreamHandler())
    for noisy in ("httpx", "httpx2", "httpcore", "huggingface_hub", "urllib3", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_lock_file = None


def acquire_single_instance() -> bool:
    """Verhindert, dass SBeach doppelt läuft (zwei Hotkeys, doppelter Text)."""
    global _lock_file
    import fcntl

    from .config import support_dir

    _lock_file = open(support_dir() / "sbeach.lock", "w")
    try:
        fcntl.flock(_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


class _Scheduler:
    def call_after(self, fn, *args):
        AppHelper.callAfter(fn, *args)

    def call_later(self, delay, fn, *args):
        AppHelper.callLater(delay, fn, *args)


# Berechtigungen -----------------------------------------------------------
def _open_privacy(anchor: str) -> None:
    NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(PRIVACY + anchor))


def microphone_granted() -> bool:
    try:
        import AVFoundation as AV

        return AV.AVCaptureDevice.authorizationStatusForMediaType_(AV.AVMediaTypeAudio) == 3
    except Exception:
        return True


def request_microphone() -> None:
    try:
        import AVFoundation as AV

        if AV.AVCaptureDevice.authorizationStatusForMediaType_(AV.AVMediaTypeAudio) == 0:
            AV.AVCaptureDevice.requestAccessForMediaType_completionHandler_(AV.AVMediaTypeAudio, lambda ok: None)
            return
    except Exception:
        pass
    _open_privacy("Privacy_Microphone")


def input_monitoring_granted() -> bool:
    try:
        import Quartz

        return bool(Quartz.CGPreflightListenEventAccess())
    except Exception:
        return True


def request_input_monitoring() -> None:
    try:
        import Quartz

        Quartz.CGRequestListenEventAccess()
    except Exception:
        pass
    _open_privacy("Privacy_ListenEvent")


def request_accessibility() -> None:
    inserter.accessibility_trusted(prompt=True)
    _open_privacy("Privacy_Accessibility")


def _login_service():
    if not str(NSBundle.mainBundle().bundlePath()).endswith(".app"):
        return None
    try:
        from ServiceManagement import SMAppService

        return SMAppService.mainAppService()
    except Exception:
        return None


# UI Brücke für den Controller --------------------------------------------
class _Bridge:
    def __init__(self, app):
        self.app = app

    def show_recording(self):
        if not self.app.main.visible():
            self.app.hud.show("recording")

    def show_transcribing(self):
        if not self.app.main.visible():
            self.app.hud.show("transcribing")

    def hide(self):
        self.app.hud.hide()

    def flash(self, message):
        if self.app.main.visible():
            self.app.main.note(message, 2.0)
        else:
            self.app.hud.flash(message)

    def play(self, sound):
        name, volume = SOUNDS.get(sound, ("Pop", 0.2))
        snd = NSSound.soundNamed_(name)
        if snd is not None:
            snd = snd.copy()
            snd.setVolume_(volume)
            snd.play()

    def state_changed(self):
        self.app.refresh()


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, notification):
        self.cfg = Config()
        cfg = self.cfg
        self.recorder = Recorder(cfg["input_device"])
        self.transcriber = Transcriber(
            model=cfg["model"], language=cfg["language"], allowed=cfg["allowed_languages"],
            fallback=cfg["fallback_language"], backend=cfg["backend"], vocabulary=cfg["vocabulary"])

        self.hud = Hud.alloc().init()
        self.hud.elapsed = self.recorder.elapsed
        self.hud.eq.level_source = self.recorder.band_levels

        self.main = MainWindow.alloc().init()
        self.main.elapsed = self.recorder.elapsed
        self.main.eq.level_source = self.recorder.band_levels

        self.settings = SettingsWindow.alloc().init()
        self.settings.on_change = self.change_setting
        self.settings.devices = input_devices
        self.settings.permissions = self.permission_rows
        self.settings.login_state = self.login_enabled
        self.settings.has_api_key = llm.get_api_key

        self.ctrl = Controller(cfg, self.recorder, self.transcriber, _Bridge(self), _Scheduler(),
                               deliver=self.deliver)
        self.main.on_record = self.ctrl.toggle
        self.main.on_settings = self.open_settings
        self.main.on_files = self.open_files
        self.main.on_open_file = self.choose_file
        self.main.root.accepts = media.supported
        self.assistant = llm.Assistant(cfg)
        self.results = []
        from concurrent.futures import ThreadPoolExecutor

        self.file_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sbeach-files")
        self.ai_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sbeach-ai")

        self.menu = StatusMenu.alloc().init()
        self.menu.state = self.ui_state
        self.menu.history = lambda: list(self.ctrl.history)
        self.menu.actions = {
            "record": self.ctrl.toggle,
            "window": self.main.toggle,
            "copy": self.copy_text,
            "settings": self.open_settings,
            "file": self.choose_file,
            "quit": lambda: NSApplication.sharedApplication().terminate_(None),
        }

        self.tap = HotkeyTap(cfg["hotkey"], lambda ev: AppHelper.callAfter(self.ctrl.on_hotkey, ev))
        self.tap_ok = self.tap.start()
        if not self.tap_ok:
            request_input_monitoring()
            self.retry = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                2.0, self, "retryTap:", None, True)
        if not inserter.accessibility_trusted():
            inserter.accessibility_trusted(prompt=True)
        if not microphone_granted():
            request_microphone()

        defaults = NSUserDefaults.standardUserDefaults()
        if not defaults.boolForKey_("SBeachLaunchedBefore"):
            defaults.setBool_forKey_(True, "SBeachLaunchedBefore")
            self.main.show()

        self.ctrl.preload()
        self.refresh()
        log.info("%s %s gestartet", APP_NAME, __version__)

    def application_openFiles_(self, app, filenames):
        """Finder: Rechtsklick › Öffnen mit › SBeach, oder Datei auf das App Symbol ziehen."""
        AppHelper.callAfter(self.open_files, [str(f) for f in filenames])
        app.replyToOpenOrPrint_(0)

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, visible):
        self.main.show()
        return True

    def retryTap_(self, timer):
        if self.tap.start():
            self.tap_ok = True
            timer.invalidate()
            self.refresh()

    # Zustand --------------------------------------------------------------
    @objc.python_method
    def ui_state(self) -> dict:
        c, cfg = self.ctrl, self.cfg
        short = HOTKEYS[cfg["hotkey"]][1]
        if not self.tap_ok:
            hint = "Kurzbefehl braucht Eingabeüberwachung"
        elif cfg["mode"] == "hold":
            hint = f"{short} halten zum Diktieren"
        else:
            hint = f"{short} drücken zum Starten"
        if c.recording:
            status_text = "Hört zu"
        elif c.pending:
            status_text = "Schreibt"
        else:
            status_text = {"loading": "Wird vorbereitet", "error": "Nicht bereit"}.get(c.status, "Bereit")
        return {
            "recording": c.recording and c.revealed,
            "pending": c.pending,
            "status": c.status,
            "status_text": status_text,
            "detail": c.status_detail[:80],
            "hint": hint,
            "loading_hint": "Sprachmodell wird geladen",
            "mode_label": f"{LANG_SHORT.get(cfg['language'], 'DE / EN')}  ·  {MODELS[cfg['model']]['label']}",
            "window_visible": self.main.visible(),
        }

    @objc.python_method
    def refresh(self) -> None:
        state = self.ui_state()
        self.main.render(state)
        self.menu.set_recording(state["recording"])

    # Einfügen -------------------------------------------------------------
    @objc.python_method
    def deliver(self, text: str) -> str:
        preview = text.strip()
        preview = preview if len(preview) <= 34 else preview[:33].rstrip() + "…"
        if inserter.secure_input_active() or not inserter.accessibility_trusted():
            self.copy_text(text.strip())
            self.main.note("In die Zwischenablage kopiert")
            return "copied"
        inserter.insert(text, self.cfg["insert_method"], self.cfg["restore_clipboard"],
                        schedule=AppHelper.callLater)
        self.main.note(f"„{preview}“ eingefügt")
        return "inserted"

    @objc.python_method
    def copy_text(self, text: str) -> None:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)

    # Dateien ---------------------------------------------------------------
    @objc.python_method
    def choose_file(self) -> None:
        from AppKit import NSApp, NSModalResponseOK, NSOpenPanel

        panel = NSOpenPanel.openPanel()
        panel.setAllowsMultipleSelection_(True)
        panel.setAllowedFileTypes_(media.EXTENSIONS)
        panel.setMessage_("Audio oder Video zum Transkribieren auswählen")
        NSApp.activateIgnoringOtherApps_(True)
        if panel.runModal() == NSModalResponseOK:
            self.open_files([str(u.path()) for u in panel.URLs()])

    @objc.python_method
    def open_files(self, paths) -> None:
        for path in paths:
            if not media.supported(path):
                self.main.note("Dateiformat nicht unterstützt")
                continue
            win = ResultWindow.alloc().initWithPath_(path)
            win.on_prompt = self.run_prompt
            win.on_close = lambda w: w in self.results and self.results.remove(w)
            win.set_provider(self.ai_label())
            self.results.append(win)
            win.show()
            self.file_pool.submit(self._transcribe_file, win, path)

    @objc.python_method
    def _transcribe_file(self, win, path) -> None:
        import time

        call = AppHelper.callAfter
        try:
            call(win.set_progress, None, "Datei wird gelesen")
            audio = media.load_audio(path)
            total = media.format_duration(audio.size / media.SAMPLE_RATE)
            started = time.monotonic()
            call(win.set_progress, 0.0, f"{total}  ·  Transkribiere …")
            segments, lang = media.transcribe_audio(
                audio, self.transcriber,
                progress=lambda f: call(win.set_progress, f, f"{total}  ·  Transkribiere … {int(f * 100)} %"))
            text = media.plain_text(segments)
            took = time.monotonic() - started
            language = {"de": "Deutsch", "en": "Englisch", "es": "Spanisch", "fr": "Französisch",
                        "it": "Italienisch", "nl": "Niederländisch", "tr": "Türkisch"}.get(lang, lang.upper())
            meta = f"{total}  ·  {language}  ·  lokal erkannt in {took:.0f} s"
            log.info("Datei transkribiert (%s, %s) in %.1fs", total, lang, took)
            call(win.set_transcript, text, segments, meta)
        except Exception as exc:
            log.exception("Datei konnte nicht transkribiert werden")
            call(win.set_error, f"Diese Datei konnte nicht gelesen werden.\n\n{exc}")

    @objc.python_method
    def ai_label(self) -> str:
        if self.cfg["ai_provider"] == "claude":
            return llm.CLAUDE_MODELS.get(self.cfg["claude_model"], "Claude").split(" (")[0]
        return "Lokal"

    @objc.python_method
    def run_prompt(self, win, instruction, label, transcript) -> None:
        win.set_provider(self.ai_label())
        win.ai_started(label)
        if self.cfg["ai_provider"] == "local" and not self.assistant.local.ready:
            win.output_state.setStringValue_("Lokales Modell wird geladen …")
        state = {"last": 0.0}

        def on_text(text):
            import time

            now = time.monotonic()
            if now - state["last"] > 0.05:
                state["last"] = now
                AppHelper.callAfter(win.ai_update, text)

        def work():
            try:
                out = self.assistant.run(instruction, transcript, on_text)
                AppHelper.callAfter(win.ai_done, out)
            except Exception as exc:
                log.exception("KI Anfrage fehlgeschlagen")
                AppHelper.callAfter(win.ai_done, None, str(exc))

        self.ai_pool.submit(work)

    # Einstellungen --------------------------------------------------------
    @objc.python_method
    def open_settings(self) -> None:
        self.settings.show(self.cfg)

    @objc.python_method
    def permission_rows(self):
        return [
            ("Mikrofon", microphone_granted(), request_microphone),
            ("Bedienungshilfen", inserter.accessibility_trusted(), request_accessibility),
            ("Eingabeüberwachung", input_monitoring_granted() and self.tap_ok, request_input_monitoring),
        ]

    @objc.python_method
    def login_enabled(self):
        service = _login_service()
        if service is None:
            return None
        return int(service.status()) == 1

    @objc.python_method
    def change_setting(self, key, value) -> None:
        if key == "login":
            service = _login_service()
            if service is not None:
                ok, err = (service.registerAndReturnError_(None) if value
                           else service.unregisterAndReturnError_(None))
                if not ok:
                    log.warning("Anmeldeobjekt nicht geändert: %s", err)
            return
        if key == "api_key":
            llm.set_api_key(value)
            self.assistant.reset_claude()
            return
        self.cfg.set(key, value)
        if key in ("ai_provider", "claude_model"):
            self.assistant.reset_claude()
            for win in self.results:
                win.set_provider(self.ai_label())
        if key == "hotkey":
            self.tap.set_key(value)
        elif key in ("model", "language", "vocabulary"):
            self.transcriber.configure(**{key: value})
            if key == "model":
                self.ctrl.preload()
        elif key == "input_device":
            self.recorder.device = value
        self.refresh()


_delegate = None


def main() -> None:
    global _delegate
    setup_logging()
    if not acquire_single_instance():
        log.info("SBeach läuft bereits, zweiter Start wird beendet")
        return
    app = NSApplication.sharedApplication()
    _delegate = AppDelegate.alloc().init()
    app.setDelegate_(_delegate)
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
