"""Gestaltungssystem: Farben (Light und Dark), Schrift, Abstände, Animation.

Alle Markenfarben sind dynamische NSColors. Sie lösen sich beim Zeichnen
automatisch für das aktuelle Erscheinungsbild auf, ohne eigene Umschaltlogik.
"""

from __future__ import annotations

import time
from pathlib import Path

import objc
from AppKit import (
    NSAppearanceNameAqua,
    NSAppearanceNameDarkAqua,
    NSBox,
    NSBoxCustom,
    NSColor,
    NSFont,
    NSImage,
    NSView,
)
from Foundation import NSObject, NSRunLoop, NSRunLoopCommonModes, NSTimer, NSZeroRect

RES = Path(__file__).resolve().parent.parent / "resources"

# Abstände im 4 pt Raster
XS, S, M, L, XL = 4.0, 8.0, 12.0, 16.0, 24.0

# Gewichte von SF Pro
REGULAR, MEDIUM, SEMIBOLD = 0.0, 0.23, 0.3

# name: (light, dark) als (hex, alpha)
PALETTE = {
    "text": (("#1D1F23", 1.0), ("#F2EFEA", 1.0)),
    "secondary": (("#1D1F23", 0.56), ("#F2EFEA", 0.60)),
    "tertiary": (("#1D1F23", 0.30), ("#F2EFEA", 0.34)),
    "hairline": (("#000000", 0.08), ("#FFFFFF", 0.10)),
    "sea": (("#23958E", 1.0), ("#4CC3B9", 1.0)),
    "ocean": (("#2A7FA8", 1.0), ("#3E9DC8", 1.0)),
    "sand": (("#BFA273", 1.0), ("#E6D3B1", 1.0)),
    "face": (("#FFFFFF", 1.0), ("#45484F", 1.0)),
    "face_hover": (("#FBFAF7", 1.0), ("#4C5057", 1.0)),
    "ring": (("#1D1F23", 0.10), ("#FFFFFF", 0.14)),
    # Off-White bzw. Anthrazit über dem Systemmaterial: ruhige Markenfläche, dezent transluzent
    "surface": (("#FAF8F4", 0.78), ("#1E2126", 0.62)),
    "shadow": (("#000000", 0.16), ("#000000", 0.45)),
}


def _hex(hex_color: str, alpha: float):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return NSColor.colorWithSRGBRed_green_blue_alpha_(r, g, b, alpha)


def is_dark(appearance) -> bool:
    if appearance is None:
        return False
    best = appearance.bestMatchFromAppearancesWithNames_([NSAppearanceNameAqua, NSAppearanceNameDarkAqua])
    return best == NSAppearanceNameDarkAqua


_cache: dict[str, object] = {}


def color(name: str):
    """Dynamische Farbe, die Light und Dark Mode selbst auflöst."""
    if name in _cache:
        return _cache[name]
    light = _hex(*PALETTE[name][0])
    dark = _hex(*PALETTE[name][1])
    try:
        dyn = NSColor.colorWithName_dynamicProvider_(
            f"sbeach.{name}", lambda appearance: dark if is_dark(appearance) else light
        )
    except Exception:  # sehr alte PyObjC Versionen
        dyn = light
    _cache[name] = dyn
    return dyn


def font(size: float, weight: float = REGULAR):
    return NSFont.systemFontOfSize_weight_(size, weight)


def mono_digits(size: float, weight: float = REGULAR):
    return NSFont.monospacedDigitSystemFontOfSize_weight_(size, weight)


def symbol(name: str, description: str, size: float = 13.0, weight: float = REGULAR):
    """SF Symbol des Systems (macOS 11+), mit einheitlicher Größe."""
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, description)
    if image is None:
        return None
    try:
        from AppKit import NSImageSymbolConfiguration

        cfg = NSImageSymbolConfiguration.configurationWithPointSize_weight_(size, weight)
        image = image.imageWithSymbolConfiguration_(cfg)
    except Exception:
        pass
    return image


def resource_image(name: str, size: float | None = None, template: bool = False):
    image = NSImage.alloc().initWithContentsOfFile_(str(RES / name))
    if image is None:
        return None
    if size:
        image.setSize_((size, size))
    image.setTemplate_(template)
    return image


def ease_toward(current: float, target: float, dt: float, speed: float = 12.0) -> float:
    """Kritisch gedämpfte Annäherung, wirkt wie eine weiche Feder."""
    k = 1.0 - pow(2.718281828, -speed * dt)
    return current + (target - current) * k


class Animator(NSObject):
    """Ein gemeinsamer 60 fps Takt, der nur läuft, solange etwas animiert."""

    def init(self):
        self = objc.super(Animator, self).init()
        if self is None:
            return None
        self.callbacks = {}
        self.timer = None
        self.last = time.monotonic()
        return self

    @objc.python_method
    def add(self, key, fn) -> None:
        self.callbacks[key] = fn
        if self.timer is None:
            self.last = time.monotonic()
            self.timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / 60.0, self, "tick:", None, True
            )
            NSRunLoop.mainRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    @objc.python_method
    def remove(self, key) -> None:
        self.callbacks.pop(key, None)
        if not self.callbacks and self.timer is not None:
            self.timer.invalidate()
            self.timer = None

    def tick_(self, timer):
        now = time.monotonic()
        dt = min(0.05, now - self.last)
        self.last = now
        for key, fn in list(self.callbacks.items()):
            try:
                keep = fn(dt)
            except Exception:
                import logging

                logging.getLogger(__name__).exception("Animation fehlgeschlagen")
                keep = False
            if keep is False:
                self.remove(key)


_animator = None


def animator() -> Animator:
    global _animator
    if _animator is None:
        _animator = Animator.alloc().init()
    return _animator


def surface(frame):
    """Getönte Fläche, die über einen NSVisualEffectView gelegt wird."""
    box = NSBox.alloc().initWithFrame_(frame)
    box.setBoxType_(NSBoxCustom)
    box.setBorderWidth_(0)
    box.setTitlePosition_(0)
    box.setFillColor_(color("surface"))
    box.setAutoresizingMask_(18)  # Breite und Höhe mitwachsen lassen
    return box


class BrandMark(NSView):
    """Das S mit Welle, in einer Variante für Hell und einer für Dunkel."""

    def initWithFrame_(self, frame):
        self = objc.super(BrandMark, self).initWithFrame_(frame)
        if self is None:
            return None
        self.light = NSImage.alloc().initWithContentsOfFile_(str(RES / "mark_light.png"))
        self.dark = NSImage.alloc().initWithContentsOfFile_(str(RES / "mark.png"))
        self.setAccessibilityElement_(False)
        return self

    def isOpaque(self):
        return False

    def viewDidChangeEffectiveAppearance(self):
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        image = self.dark if is_dark(self.effectiveAppearance()) else self.light
        if image is not None:
            image.drawInRect_fromRect_operation_fraction_(self.bounds(), NSZeroRect, 2, 1.0)
