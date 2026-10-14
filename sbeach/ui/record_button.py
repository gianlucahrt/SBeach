"""Der zentrale Aufnahmeknopf.

Eine helle Scheibe mit feiner Kontur und weichem Schatten. Im Ruhezustand liegt
darin ein Punkt in Meeresfarbe, während der Aufnahme verwandelt er sich fließend
in ein abgerundetes Quadrat (Stopp), umgeben von einem ruhig atmenden Halo.
Reagiert sofort auf Hover und Druck, ohne der aktiven App den Fokus zu nehmen.
"""

from __future__ import annotations

import math

import objc
from AppKit import (
    NSAccessibilityButtonRole,
    NSBezierPath,
    NSGraphicsContext,
    NSShadow,
    NSTrackingActiveAlways,
    NSTrackingArea,
    NSTrackingInVisibleRect,
    NSTrackingMouseEnteredAndExited,
    NSView,
)
from Foundation import NSMakeRect, NSMakeSize

from . import theme


class RecordButton(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(RecordButton, self).initWithFrame_(frame)
        if self is None:
            return None
        self.on_press = None
        self.recording = False
        self.enabled = True
        self.hover = False
        self.pressed = False
        self.p = 0.0        # 0 = Punkt, 1 = Stopp Quadrat
        self.scale = 1.0
        self.hover_mix = 0.0
        self.breath = 0.0
        self._tracking = None
        self.setAccessibilityLabel_("Diktat starten")
        return self

    # Zustand ------------------------------------------------------------
    @objc.python_method
    def set_recording(self, recording: bool) -> None:
        if recording != self.recording:
            self.recording = recording
            self._animate()
            self.setAccessibilityLabel_("Aufnahme stoppen" if recording else "Diktat starten")

    @objc.python_method
    def set_enabled(self, enabled: bool) -> None:
        if enabled != self.enabled:
            self.enabled = enabled
            self.setNeedsDisplay_(True)

    @objc.python_method
    def _animate(self) -> None:
        theme.animator().add(("rec", id(self)), self._step)

    @objc.python_method
    def _step(self, dt: float):
        self.p = theme.ease_toward(self.p, 1.0 if self.recording else 0.0, dt, 16.0)
        target_scale = 0.95 if self.pressed else 1.0
        self.scale = theme.ease_toward(self.scale, target_scale, dt, 28.0)
        self.hover_mix = theme.ease_toward(self.hover_mix, 1.0 if self.hover and self.enabled else 0.0, dt, 18.0)
        if self.recording:
            self.breath = (self.breath + dt / 1.6) % 1.0
        self.setNeedsDisplay_(True)
        settled = (abs(self.p - (1.0 if self.recording else 0.0)) < 0.002
                   and abs(self.scale - target_scale) < 0.002
                   and abs(self.hover_mix - (1.0 if self.hover else 0.0)) < 0.01)
        return self.recording or not settled

    # Zeichnen -----------------------------------------------------------
    def isOpaque(self):
        return False

    def viewDidChangeEffectiveAppearance(self):
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        b = self.bounds()
        cx, cy = b.size.width / 2.0, b.size.height / 2.0
        radius = 31.0 * self.scale

        # Halo während der Aufnahme: ein Ring, der sich sanft ausdehnt und verblasst
        if self.p > 0.01:
            t = self.breath
            ease = 1.0 - (1.0 - t) ** 3
            halo_r = radius + 3.0 + 9.0 * ease
            halo = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - halo_r, cy - halo_r, halo_r * 2, halo_r * 2))
            theme.color("sea").colorWithAlphaComponent_(0.28 * (1.0 - ease) * self.p).set()
            halo.setLineWidth_(1.5)
            halo.stroke()

        # Scheibe mit weichem Schatten
        face_rect = NSMakeRect(cx - radius, cy - radius, radius * 2, radius * 2)
        face = NSBezierPath.bezierPathWithOvalInRect_(face_rect)
        NSGraphicsContext.saveGraphicsState()
        shadow = NSShadow.alloc().init()
        shadow.setShadowColor_(theme.color("shadow"))
        shadow.setShadowOffset_(NSMakeSize(0, -1.5))
        shadow.setShadowBlurRadius_(7.0)
        shadow.set()
        (theme.color("face_hover") if self.hover_mix > 0.5 else theme.color("face")).set()
        face.fill()
        NSGraphicsContext.restoreGraphicsState()
        theme.color("ring").set()
        face.setLineWidth_(0.75)
        face.stroke()

        # Glyphe: Punkt -> abgerundetes Quadrat
        p = self.p
        size = (24.0 + (20.0 - 24.0) * p) * self.scale
        corner = size / 2.0 + (5.0 - size / 2.0) * p
        glyph = NSMakeRect(cx - size / 2.0, cy - size / 2.0, size, size)
        tone = theme.color("sea") if self.enabled else theme.color("tertiary")
        tone.set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(glyph, corner, corner).fill()

    # Interaktion --------------------------------------------------------
    def acceptsFirstMouse_(self, event):
        return True

    def updateTrackingAreas(self):
        if self._tracking is not None:
            self.removeTrackingArea_(self._tracking)
        opts = NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways | NSTrackingInVisibleRect
        self._tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), opts, self, None)
        self.addTrackingArea_(self._tracking)
        objc.super(RecordButton, self).updateTrackingAreas()

    def mouseEntered_(self, event):
        self.hover = True
        self._animate()

    def mouseExited_(self, event):
        self.hover = False
        self.pressed = False
        self._animate()

    @objc.python_method
    def _inside(self, event) -> bool:
        pt = self.convertPoint_fromView_(event.locationInWindow(), None)
        b = self.bounds()
        return math.hypot(pt.x - b.size.width / 2.0, pt.y - b.size.height / 2.0) <= 36.0

    def mouseDown_(self, event):
        if not self.enabled or not self._inside(event):
            return
        self.pressed = True
        self._animate()

    def mouseUp_(self, event):
        was = self.pressed
        self.pressed = False
        self._animate()
        if was and self._inside(event) and self.on_press is not None:
            self.on_press()

    # Bedienungshilfen ---------------------------------------------------
    def isAccessibilityElement(self):
        return True

    def accessibilityRole(self):
        return NSAccessibilityButtonRole

    def accessibilityPerformPress(self):
        if self.enabled and self.on_press is not None:
            self.on_press()
        return True
