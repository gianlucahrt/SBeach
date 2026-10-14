"""Aufnahme HUD: eine kleine, schwebende Kapsel am unteren Bildschirmrand.

Erscheint nur während Aufnahme und Transkription, wenn das Hauptfenster
geschlossen ist. Transluzent, mit feiner Kontur, folgt Light und Dark Mode.
Klicks gehen durch die Kapsel hindurch, der Fokus bleibt in der Ziel App.
"""

from __future__ import annotations

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEvent,
    NSLineBreakByTruncatingTail,
    NSPanel,
    NSScreen,
    NSStatusWindowLevel,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
    NSTextField,
    NSView,
    NSVisualEffectView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorIgnoresCycle,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSInsetRect, NSMakePoint, NSMakeRect, NSObject, NSPointInRect
from PyObjCTools import AppHelper

from . import theme
from .equalizer import EqualizerView

WIDTH, HEIGHT = 212.0, 40.0
BOTTOM_OFFSET = 72.0
MATERIAL_POPOVER = 6


class _Outline(NSView):
    """Feine Kontur über der Kapsel, passend zum Erscheinungsbild."""

    def isOpaque(self):
        return False

    def viewDidChangeEffectiveAppearance(self):
        self.setNeedsDisplay_(True)

    def hitTest_(self, point):
        return None

    def drawRect_(self, rect):
        b = NSInsetRect(self.bounds(), 0.5, 0.5)
        r = b.size.height / 2.0
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, r, r)
        theme.color("hairline").set()
        path.setLineWidth_(1.0)
        path.stroke()


class Hud(NSObject):
    def init(self):
        self = objc.super(Hud, self).init()
        if self is None:
            return None
        self.token = 0
        self.shown = False
        self.elapsed = None
        self._build()
        return self

    @objc.python_method
    def _build(self) -> None:
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, HEIGHT),
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered, False)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setLevel_(NSStatusWindowLevel)
        panel.setIgnoresMouseEvents_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setReleasedWhenClosed_(False)
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary | NSWindowCollectionBehaviorIgnoresCycle)
        panel.setAlphaValue_(0.0)

        effect = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        effect.setMaterial_(MATERIAL_POPOVER)
        effect.setBlendingMode_(0)
        effect.setState_(1)
        effect.setWantsLayer_(True)
        effect.layer().setCornerRadius_(HEIGHT / 2.0)
        effect.layer().setMasksToBounds_(True)
        panel.setContentView_(effect)
        effect.addSubview_(theme.surface(effect.bounds()))
        effect.addSubview_(theme.BrandMark.alloc().initWithFrame_(NSMakeRect(14, (HEIGHT - 18) / 2.0, 18, 18)))

        self.eq = EqualizerView.alloc().initWithFrame_(NSMakeRect(44, 8, 112, HEIGHT - 16))
        self.eq.configure(16, 2.5)
        effect.addSubview_(self.eq)

        self.clock = NSTextField.labelWithString_("0:00")
        self.clock.setFont_(theme.mono_digits(12.0, theme.MEDIUM))
        self.clock.setTextColor_(NSColor.secondaryLabelColor())
        self.clock.setAlignment_(NSTextAlignmentRight)
        self.clock.setFrame_(NSMakeRect(WIDTH - 16 - 38, (HEIGHT - 16) / 2.0, 38, 16))
        effect.addSubview_(self.clock)

        self.message = NSTextField.labelWithString_("")
        self.message.setFont_(theme.font(12.0, theme.MEDIUM))
        self.message.setTextColor_(NSColor.labelColor())
        self.message.setAlignment_(NSTextAlignmentCenter)
        self.message.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
        self.message.setFrame_(NSMakeRect(40, (HEIGHT - 16) / 2.0, WIDTH - 56, 16))
        self.message.setHidden_(True)
        effect.addSubview_(self.message)

        outline = _Outline.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        effect.addSubview_(outline)

        self.panel = panel

    # API ----------------------------------------------------------------
    @objc.python_method
    def show(self, mode: str) -> None:
        self.token += 1
        self.message.setHidden_(True)
        self.eq.setHidden_(False)
        self.clock.setHidden_(mode != "recording")
        self.eq.set_mode(mode)
        if mode == "recording":
            self.clock.setStringValue_("0:00")
            theme.animator().add(("hudclock", id(self)), self._tick)
        self._appear()

    @objc.python_method
    def flash(self, text: str, seconds: float = 1.6) -> None:
        self.token += 1
        token = self.token
        self.eq.set_mode("idle")
        self.eq.setHidden_(True)
        self.clock.setHidden_(True)
        self.message.setStringValue_(text)
        self.message.setHidden_(False)
        self._appear()
        AppHelper.callLater(seconds, lambda: self.token == token and self.hide())

    @objc.python_method
    def hide(self) -> None:
        if not self.shown:
            return
        self.shown = False
        self.token += 1
        token = self.token
        self.eq.set_mode("idle")

        def finished():
            if self.token == token and not self.shown:
                self.panel.orderOut_(None)

        self._fade(0.0, 0.18, finished)

    # Intern -------------------------------------------------------------
    @objc.python_method
    def _tick(self, dt: float):
        if self.elapsed is None or self.eq.mode != "recording" or not self.shown:
            return False
        secs = int(self.elapsed())
        self.clock.setStringValue_(f"{secs // 60}:{secs % 60:02d}")
        return True

    @objc.python_method
    def _appear(self) -> None:
        if self.shown:
            return
        self.shown = True
        self._position()
        self.panel.orderFrontRegardless()
        self._fade(1.0, 0.16)

    @objc.python_method
    def _fade(self, alpha: float, duration: float, completion=None) -> None:
        from AppKit import NSAnimationContext

        panel = self.panel

        def changes(ctx):
            ctx.setDuration_(duration)
            panel.animator().setAlphaValue_(alpha)

        NSAnimationContext.runAnimationGroup_completionHandler_(
            changes, (lambda: completion()) if completion else (lambda: None))

    @objc.python_method
    def _position(self) -> None:
        mouse = NSEvent.mouseLocation()
        screen = NSScreen.mainScreen()
        for candidate in NSScreen.screens():
            if NSPointInRect(mouse, candidate.frame()):
                screen = candidate
                break
        frame = screen.visibleFrame()
        x = frame.origin.x + (frame.size.width - WIDTH) / 2.0
        self.panel.setFrameOrigin_(NSMakePoint(x, frame.origin.y + BOTTOM_OFFSET))
