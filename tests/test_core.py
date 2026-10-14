"""Tests der plattformunabhängigen Kernlogik (laufen auch ohne macOS)."""

import json
from concurrent.futures import Future

import numpy as np
import pytest

from sbeach import textproc
from sbeach.config import DEFAULTS, Config
from sbeach.controller import CHORD_GRACE, Controller
from sbeach.hotkey import HOTKEYS, NX_DEVICERALTKEYMASK, HotkeyLogic
from sbeach.levels import compute_bands
from sbeach.transcriber import Transcriber

SR = 16000


def tone(seconds=1.0, amp=0.2, freq=220.0):
    t = np.arange(int(SR * seconds)) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


# Konfiguration -------------------------------------------------------------
def test_config_defaults_and_validation(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"mode": "quatsch", "model": "precise", "unbekannt": 1}))
    cfg = Config(path)
    assert cfg["mode"] == DEFAULTS["mode"]
    assert cfg["model"] == "precise"
    assert "unbekannt" not in cfg.data
    cfg.set("mode", "toggle")
    assert json.loads(path.read_text())["mode"] == "toggle"
    with pytest.raises(ValueError):
        cfg.set("insert_method", "telepathie")


def test_config_survives_broken_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{kaputt")
    assert Config(path)["hotkey"] == "alt_r"


# Textverarbeitung ----------------------------------------------------------
def test_silence_detection():
    assert textproc.is_silent(np.zeros(SR, dtype=np.float32))
    assert textproc.is_silent(tone(0.1))  # zu kurz
    assert not textproc.is_silent(tone(1.0))


def test_clean_drops_hallucinations():
    assert textproc.clean("Untertitel der Amara.org-Community") == ""
    assert textproc.clean("Vielen Dank.", quiet=True) == ""
    assert textproc.clean("Vielen Dank.", quiet=False) == "Vielen Dank. "
    assert textproc.clean("  Hallo   Welt ", trailing_space=False) == "Hallo Welt"
    assert textproc.clean("das das das das das ist gut", trailing_space=False) == "das ist gut"


def test_prompt_from_vocabulary():
    assert textproc.build_prompt([]) is None
    assert textproc.build_prompt(["SBeach", " Saxion ", ""]) == "SBeach, Saxion."


# Equalizer -----------------------------------------------------------------
def test_bands_react_to_frequency():
    low = compute_bands(tone(0.032, 0.3, 150.0)[:512], 18)
    high = compute_bands(tone(0.032, 0.3, 4000.0)[:512], 18)
    assert low.shape == (18,) and 0 <= low.min() and low.max() <= 1
    assert low[:6].mean() > low[-6:].mean()
    assert high[-6:].mean() > high[:6].mean()
    assert compute_bands(np.zeros(512, np.float32), 18).max() == 0


# Hotkey --------------------------------------------------------------------
def test_modifier_hold_and_release():
    logic = HotkeyLogic("alt_r")
    code = HOTKEYS["alt_r"][2]
    assert logic.feed("flags", code, NX_DEVICERALTKEYMASK) == ["down"]
    assert logic.feed("flags", code, NX_DEVICERALTKEYMASK) == []  # kein Doppel
    assert logic.feed("flags", code, 0) == ["up"]


def test_modifier_chord_like_at_sign():
    logic = HotkeyLogic("alt_r")
    code = HOTKEYS["alt_r"][2]
    logic.feed("flags", code, NX_DEVICERALTKEYMASK)
    assert logic.feed("keydown", 37) == ["chord"]  # ⌥ + L
    assert logic.feed("keydown", 37) == []
    assert logic.feed("flags", code, 0) == ["up_chord"]


def test_left_option_does_not_trigger():
    logic = HotkeyLogic("alt_r")
    assert logic.feed("flags", 58, 0x80000 | 0x20) == []


def test_function_key_ignores_autorepeat():
    logic = HotkeyLogic("f13")
    code = HOTKEYS["f13"][2]
    assert logic.feed("keydown", code) == ["down"]
    assert logic.feed("keydown", code, autorepeat=True) == []
    assert logic.feed("keyup", code) == ["up"]
    assert logic.feed("keydown", 53) == ["escape"]


# Ablaufsteuerung -----------------------------------------------------------
class FakeRecorder:
    def __init__(self):
        self.audio = tone(1.0)
        self.t = 0.0
        self.active = False

    def start(self):
        self.active = True

    def stop(self):
        self.active = False
        return self.audio

    def cancel(self):
        self.active = False

    def elapsed(self):
        return self.t


class FakeTranscriber:
    def __init__(self, text="Hallo Welt", fail=False):
        self.text, self.fail = text, fail

    def load(self):
        pass

    def transcribe(self, audio):
        if self.fail:
            raise RuntimeError("kaputt")
        return self.text, "de"


class SyncExecutor:
    def submit(self, fn, *args):
        fut = Future()
        try:
            fut.set_result(fn(*args))
        except Exception as exc:
            fut.set_exception(exc)
        return fut


class FakeScheduler:
    def __init__(self):
        self.later = []

    def call_after(self, fn, *args):
        fn(*args)

    def call_later(self, delay, fn, *args):
        self.later.append((fn, args))

    def run_later(self):
        jobs, self.later = self.later, []
        for fn, args in jobs:
            fn(*args)


class FakeUI:
    def __init__(self):
        self.events = []

    def show_recording(self): self.events.append("rec")
    def show_transcribing(self): self.events.append("asr")
    def hide(self): self.events.append("hide")
    def flash(self, m): self.events.append(f"flash:{m}")
    def play(self, s): self.events.append(f"sound:{s}")
    def state_changed(self): pass


def make(tmp_path, mode="hold", **kw):
    cfg = Config(tmp_path / "c.json")
    cfg.set("mode", mode)
    delivered = []
    ui, sched, rec = FakeUI(), FakeScheduler(), FakeRecorder()
    ctrl = Controller(cfg, rec, kw.get("asr", FakeTranscriber()), ui, sched,
                      deliver=lambda t: delivered.append(t) or "inserted",
                      executor=SyncExecutor())
    return ctrl, ui, sched, rec, delivered


def test_hold_flow_inserts_text(tmp_path):
    ctrl, ui, sched, rec, delivered = make(tmp_path)
    ctrl.on_hotkey("down")
    assert rec.active and "rec" not in ui.events  # Overlay noch verzögert
    sched.run_later()
    assert "rec" in ui.events
    rec.t = 2.0
    ctrl.on_hotkey("up")
    assert delivered == ["Hallo Welt "]
    assert list(ctrl.history) == ["Hallo Welt"]
    assert ui.events[-1] == "hide" or "hide" in ui.events


def test_hold_chord_cancels_silently(tmp_path):
    ctrl, ui, sched, rec, delivered = make(tmp_path)
    ctrl.on_hotkey("down")
    rec.t = CHORD_GRACE / 2
    ctrl.on_hotkey("chord")
    sched.run_later()
    ctrl.on_hotkey("up_chord")
    assert not ctrl.recording and delivered == []
    assert "rec" not in ui.events


def test_short_tap_is_ignored(tmp_path):
    ctrl, ui, sched, rec, delivered = make(tmp_path)
    ctrl.on_hotkey("down")
    rec.t = 0.1
    ctrl.on_hotkey("up")
    assert delivered == []


def test_toggle_mode(tmp_path):
    ctrl, ui, sched, rec, delivered = make(tmp_path, mode="toggle")
    ctrl.on_hotkey("down")
    assert not ctrl.recording
    ctrl.on_hotkey("up")
    assert ctrl.recording and "rec" in ui.events
    rec.t = 3.0
    ctrl.on_hotkey("down")
    ctrl.on_hotkey("up")
    assert delivered == ["Hallo Welt "]
    ctrl.on_hotkey("up_chord")  # Kombination startet nichts
    assert not ctrl.recording


def test_escape_cancels(tmp_path):
    ctrl, ui, sched, rec, delivered = make(tmp_path, mode="toggle")
    ctrl.toggle()
    ctrl.on_hotkey("escape")
    assert not ctrl.recording and delivered == []
    assert "sound:cancel" in ui.events


def test_silence_gives_feedback(tmp_path):
    ctrl, ui, sched, rec, delivered = make(tmp_path, mode="toggle")
    rec.audio = np.zeros(SR, np.float32)
    ctrl.toggle()
    rec.t = 1.0
    ctrl.toggle()
    assert delivered == [] and "flash:Nichts gehört" in ui.events


def test_transcription_error_is_reported(tmp_path):
    ctrl, ui, sched, rec, delivered = make(tmp_path, mode="toggle", asr=FakeTranscriber(fail=True))
    ctrl.toggle()
    rec.t = 1.0
    ctrl.toggle()
    assert ctrl.status == "error" and "flash:Erkennung fehlgeschlagen" in ui.events


def test_preload_sets_ready(tmp_path):
    ctrl, *_ = make(tmp_path)
    ctrl.preload()
    assert ctrl.status == "ready"


# Spracherkennung (Sprachbeschränkung mit Fake Backend) ---------------------
def test_language_restricted_to_allowed(monkeypatch):
    class Info:
        def __init__(self, lang):
            self.language = lang
            self.all_language_probs = [("nl", 0.6), ("de", 0.3), ("en", 0.1)]

    class Seg:
        def __init__(self, text):
            self.text, self.start, self.end = text, 0.0, 1.0

    calls = []

    class FakeModel:
        def transcribe(self, audio, language=None, **kw):
            calls.append(language)
            return iter([Seg(" Hallo")]), Info(language or "nl")

    tr = Transcriber(backend="faster-whisper")
    tr.backend = "faster-whisper"
    tr._fw_model = FakeModel()
    text, lang, _ = tr._run(np.zeros(SR, np.float32), None)
    assert calls == [None, "de"] and lang == "de" and text == "Hallo"
