"""Selbstprüfung der Oberfläche: rendert alle Fenster und Zustände als PNG.

Aufruf:  python -m sbeach --snapshot <Ordner>
Erzeugt je Zustand ein Bild in Hell und Dunkel, mit den echten Views der App.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from AppKit import (
    NSAppearance,
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSBitmapImageFileTypePNG,
    NSColor,
    NSView,
)
from Foundation import NSMakeRect

from .config import Config
from .ui.hud import Hud
from .ui.main_window import MainWindow
from .ui.result_window import ResultWindow
from .ui.settings import SettingsWindow

SAMPLE_TEXT = (
    "Drei Tipps für deinen ersten Marathon. Erstens: Lauf die ersten zehn Kilometer bewusst langsamer, "
    "als du dich fühlst. Die meisten verlieren das Rennen nicht am Ende, sondern am Anfang. "
    "Zweitens: Trainiere deine Verpflegung, nicht nur deine Beine. Teste Gels und Getränke in den "
    "langen Läufen, nie erst am Wettkampftag.\n\nUnd drittens: Plane die letzten zwölf Kilometer "
    "mental. Teile sie in kleine Abschnitte und hake jeden einzeln ab."
)
SAMPLE_OUT = (
    "• Die ersten 10 km bewusst langsamer laufen als gefühlt\n"
    "• Verpflegung (Gels, Getränke) in langen Trainingsläufen testen\n"
    "• Die letzten 12 km mental in kleine Abschnitte teilen"
)

STATE = {
    "recording": False, "pending": 0, "status": "ready", "status_text": "Bereit",
    "detail": "", "hint": "⌥ rechts halten zum Diktieren", "loading_hint": "Sprachmodell wird geladen",
    "mode_label": "DE / EN  ·  Ausgewogen", "window_visible": True,
}


def fake_levels(n, t=[0.0]):
    t[0] += 0.37
    return [max(0.0, 0.55 + 0.4 * math.sin(i * 0.9 + t[0]) * math.cos(i * 0.31)) for i in range(n)]


class _Backdrop(NSView):
    def drawRect_(self, rect):
        self.backdrop.set()
        from AppKit import NSRectFill

        NSRectFill(self.bounds())


def capture(window, path: Path, dark: bool, pad: float = 24.0) -> None:
    """Rendert den Fensterinhalt auf einen neutralen Hintergrund (wie ein Desktop)."""
    content = window.contentView()
    frame = content.frame()
    w, h = frame.size.width + 2 * pad, frame.size.height + 2 * pad
    host = _Backdrop.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    host.backdrop = NSColor.colorWithSRGBRed_green_blue_alpha_(
        *((0.16, 0.17, 0.19, 1) if dark else (0.86, 0.87, 0.89, 1)))
    rep = host.bitmapImageRepForCachingDisplayInRect_(host.bounds())
    host.cacheDisplayInRect_toBitmapImageRep_(host.bounds(), rep)
    inner = content.bitmapImageRepForCachingDisplayInRect_(content.bounds())
    content.cacheDisplayInRect_toBitmapImageRep_(content.bounds(), inner)
    from AppKit import NSGraphicsContext

    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    inner.drawInRect_fromRect_operation_fraction_respectFlipped_hints_(
        NSMakeRect(pad, pad, frame.size.width, frame.size.height),
        NSMakeRect(0, 0, 0, 0), 2, 1.0, True, None)
    NSGraphicsContext.restoreGraphicsState()
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    data.writeToFile_atomically_(str(path), True)


def settle(*steps):
    for _ in range(90):
        for fn in steps:
            fn(1 / 60)


def run(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

    for dark in (False, True):
        tag = "dark" if dark else "light"
        appearance = NSAppearance.appearanceNamed_(NSAppearanceNameDarkAqua if dark else NSAppearanceNameAqua)
        NSApplication.sharedApplication().setAppearance_(appearance)

        main = MainWindow.alloc().init()
        main.panel.setAppearance_(appearance)
        main.eq.level_source = fake_levels
        main.elapsed = lambda: 7.0

        main.render(dict(STATE))
        settle(main.eq._step, main.button._step)
        capture(main.panel, out / f"main_ready_{tag}.png", dark)

        main.render(dict(STATE, recording=True, status_text="Hört zu"))
        settle(main.eq._step, main.button._step)
        main.button.breath = 0.35
        main._render_subtitle()
        capture(main.panel, out / f"main_recording_{tag}.png", dark)

        main.render(dict(STATE, pending=1))
        settle(main.eq._step, main.button._step)
        capture(main.panel, out / f"main_transcribing_{tag}.png", dark)

        main.render(dict(STATE, status="loading"))
        settle(main.eq._step, main.button._step)
        capture(main.panel, out / f"main_loading_{tag}.png", dark)

        hud = Hud.alloc().init()
        hud.panel.setAppearance_(appearance)
        hud.eq.level_source = fake_levels
        hud.eq.set_mode("recording")
        hud.clock.setStringValue_("0:07")
        settle(hud.eq._step)
        capture(hud.panel, out / f"hud_recording_{tag}.png", dark)

        res = ResultWindow.alloc().initWithPath_("/Users/demo/Downloads/tiktok_marathon_tipps.mp4")
        res.window.setAppearance_(appearance)
        res.set_provider("Lokal")
        res.set_progress(0.42, "0:58  ·  Transkribiere … 42 %")
        res.window.contentView().layoutSubtreeIfNeeded()
        capture(res.window, out / f"result_progress_{tag}.png", dark)
        res.set_transcript(SAMPLE_TEXT, [(0.0, 58.0, SAMPLE_TEXT)], "0:58  ·  Deutsch  ·  lokal erkannt in 4 s")
        res.ai_started("Stichpunkte")
        res.ai_done(SAMPLE_OUT)
        res.window.contentView().layoutSubtreeIfNeeded()
        capture(res.window, out / f"result_done_{tag}.png", dark)

        settings = SettingsWindow.alloc().init()
        settings.devices = lambda: [(0, "MacBook Air Mikrofon")]
        settings.permissions = lambda: [("Mikrofon", True, None), ("Bedienungshilfen", True, None),
                                        ("Eingabeüberwachung", False, lambda: None)]
        settings.login_state = lambda: False
        settings.has_api_key = lambda: False
        settings.cfg = Config()
        settings._build()
        settings.window.setAppearance_(appearance)
        settings.window.contentView().layoutSubtreeIfNeeded()
        capture(settings.window, out / f"settings_{tag}.png", dark)
        settings.cfg.data["ai_provider"] = "claude"
        settings._build()
        settings.window.setAppearance_(appearance)
        settings.window.contentView().layoutSubtreeIfNeeded()
        capture(settings.window, out / f"settings_claude_{tag}.png", dark)
        settings.cfg.data["ai_provider"] = "local"

    print(f"Snapshots in {out}")


if __name__ == "__main__":
    run(Path(sys.argv[1] if len(sys.argv) > 1 else "snapshots"))
