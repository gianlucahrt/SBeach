"""Minimalistischer Equalizer.

Ruhe: eine Reihe feiner Punkte. Aufnahme: Balken, die mit einer weichen
Hüllkurve zur Mitte hin auf die Stimme reagieren. Transkription: eine ruhige,
wandernde Welle in Sand. Übergänge zwischen den Zuständen sind animiert.
"""

from __future__ import annotations

import math

import objc
from AppKit import NSBezierPath, NSView
from Foundation import NSMakeRect

from . import theme


class EqualizerView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(EqualizerView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.bars = 24
        self.bar_width = 3.0
        self.mode = "idle"
        self.morph = 0.0          # 0 = Punkte, 1 = Balken
        self.levels = [0.0] * self.bars
        self.phase = 0.0
        self.level_source = None  # callable(n) -> Pegel 0..1
        return self

    @objc.python_method
    def configure(self, bars: int, bar_width: float) -> None:
        self.bars = bars
        self.bar_width = bar_width
        self.levels = [0.0] * bars
        self.setNeedsDisplay_(True)

    def isOpaque(self):
        return False

    def viewDidChangeEffectiveAppearance(self):
        self.setNeedsDisplay_(True)

    @objc.python_method
    def set_mode(self, mode: str) -> None:
        if mode == self.mode:
            return
        self.mode = mode
        theme.animator().add(("eq", id(self)), self._step)

    @objc.python_method
    def _step(self, dt: float):
        target = 0.0 if self.mode == "idle" else 1.0
        self.morph = theme.ease_toward(self.morph, target, dt, 14.0)
        if self.mode == "recording" and self.level_source is not None:
            incoming = list(self.level_source(self.bars))
            new = []
            for cur, tgt in zip(self.levels, incoming):
                tgt = float(tgt)
                # schneller Anstieg, langsames Abklingen
                new.append(theme.ease_toward(cur, tgt, dt, 30.0) if tgt > cur else cur * pow(0.06, dt))
            self.levels = new
        else:
            self.levels = [lv * pow(0.02, dt) for lv in self.levels]
        if self.mode == "transcribing":
            self.phase += dt * 5.0
        self.setNeedsDisplay_(True)
        settled = abs(self.morph - target) < 0.002 and max(self.levels, default=0) < 0.002
        return not (self.mode == "idle" and settled)

    def drawRect_(self, rect):
        b = self.bounds()
        w, h = b.size.width, b.size.height
        n = self.bars
        bw = self.bar_width
        gap = (w - n * bw) / max(1, n - 1)
        mid_y = h / 2.0
        m = self.morph
        for i in range(n):
            t = i / max(1, n - 1)
            envelope = 0.35 + 0.65 * math.sin(math.pi * t) ** 1.2
            if self.mode == "transcribing":
                wave = 0.5 + 0.5 * math.sin(self.phase - i * 0.45)
                level = (0.10 + 0.28 * wave) * envelope
                theme.color("sand").colorWithAlphaComponent_(0.45 + 0.55 * wave).set()
            else:
                level = self.levels[i] * envelope
                if m < 0.5:
                    theme.color("tertiary").set()
                else:
                    tone = theme.color("sea") if t < 0.5 else theme.color("ocean")
                    tone.colorWithAlphaComponent_(0.55 + 0.45 * min(1.0, level * 1.4)).set()
            bar_h = bw + m * (max(0.0, level) * (h - bw) + 2.0 * (1.0 - level))
            bar_h = min(h, max(bw, bar_h))
            x = i * (bw + gap)
            r = NSMakeRect(x, mid_y - bar_h / 2.0, bw, bar_h)
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(r, bw / 2.0, bw / 2.0).fill()
