"""Das Hauptfenster: Aufnahmeknopf, Equalizer, Status und dezente Modusanzeige.

Ein schwebendes, nicht aktivierendes Panel. Ein Klick auf den Knopf nimmt der
App, in die diktiert wird, nicht den Fokus. Deshalb landet der Text dort, wo
der Cursor gerade steht.
"""

from __future__ import annotations

import time

import objc
from AppKit import (
    NSAttributedString,
    NSBackingStoreBuffered,
    NSBox,
    NSBoxCustom,
    NSButton,
    NSColor,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSLineBreakByTruncatingTail,
    NSPanel,
    NSTextAlignmentCenter,
    NSTextField,
    NSView,
    NSVisualEffectView,
    NSWindowMiniaturizeButton,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskTitled,
    NSWindowTitleHidden,
    NSWindowZoomButton,
)
from Foundation import NSMakeRect, NSObject
from PyObjCTools import AppHelper

from . import theme
from .equalizer import EqualizerView
from .record_button import RecordButton

WIDTH, HEIGHT = 300.0, 320.0
MATERIAL_POPOVER = 6
BLEND_BEHIND_WINDOW = 0
STATE_ACTIVE = 1


def _label(text: str, size: float, weight: float, color, frame, centered=True):
    field = NSTextField.labelWithString_(text)
    field.setFont_(theme.font(size, weight))
    field.setTextColor_(color)
    field.setFrame_(frame)
    if centered:
        field.setAlignment_(NSTextAlignmentCenter)
    field.cell().setLineBreakMode_(NSLineBreakByTruncatingTail)
    return field


def _plain_button(title: str, target, action: str, frame, color):
    button = NSButton.buttonWithTitle_target_action_(title, target, action)
    button.setBordered_(False)
    button.setFrame_(frame)
    _set_button_title(button, title, color)
    return button


def _set_button_title(button, title, color):
    attrs = {NSFontAttributeName: theme.font(11.0, theme.MEDIUM), NSForegroundColorAttributeName: color}
    button.setAttributedTitle_(NSAttributedString.alloc().initWithString_attributes_(title, attrs))


class DropView(NSVisualEffectView):
    """Hintergrund des Hauptfensters, nimmt Audio und Videodateien per Drag and Drop an."""

    def initWithFrame_(self, frame):
        self = objc.super(DropView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.on_files = None
        self.on_hover = None
        self.accepts = lambda path: True
        from AppKit import NSPasteboardTypeFileURL

        self.registerForDraggedTypes_([NSPasteboardTypeFileURL])
        return self

    @objc.python_method
    def _paths(self, info):
        from AppKit import NSURL as _URL

        urls = info.draggingPasteboard().readObjectsForClasses_options_([_URL], None) or []
        return [str(u.path()) for u in urls if u.isFileURL() and self.accepts(str(u.path()))]

    def draggingEntered_(self, info):
        ok = bool(self._paths(info))
        if self.on_hover is not None:
            self.on_hover(ok)
        return 1 if ok else 0  # NSDragOperationCopy

    def draggingExited_(self, info):
        if self.on_hover is not None:
            self.on_hover(False)

    def performDragOperation_(self, info):
        paths = self._paths(info)
        if self.on_hover is not None:
            self.on_hover(False)
        if paths and self.on_files is not None:
            self.on_files(paths)
        return bool(paths)


class _DropRing(NSView):
    def isOpaque(self):
        return False

    def hitTest_(self, point):
        return None

    def drawRect_(self, rect):
        from AppKit import NSBezierPath
        from Foundation import NSInsetRect

        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(NSInsetRect(self.bounds(), 5, 5), 12, 12)
        path.setLineWidth_(2.0)
        path.setLineDash_count_phase_([6.0, 4.0], 2, 0.0)
        theme.color("sea").set()
        path.stroke()


class MainWindow(NSObject):
    def init(self):
        self = objc.super(MainWindow, self).init()
        if self is None:
            return None
        self.on_record = None
        self.on_settings = None
        self.on_files = None
        self.on_open_file = None
        self.dropping = False
        self.elapsed = None
        self.note_text = ""
        self.note_until = 0.0
        self.state = {}
        self._build()
        return self

    # Aufbau -------------------------------------------------------------
    @objc.python_method
    def _build(self) -> None:
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
                 | NSWindowStyleMaskFullSizeContentView | NSWindowStyleMaskNonactivatingPanel)
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, HEIGHT), style, NSBackingStoreBuffered, False)
        panel.setTitle_("SBeach")
        panel.setTitleVisibility_(NSWindowTitleHidden)
        panel.setTitlebarAppearsTransparent_(True)
        panel.setMovableByWindowBackground_(True)
        panel.setFloatingPanel_(True)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setReleasedWhenClosed_(False)
        panel.setDelegate_(self)
        for kind in (NSWindowMiniaturizeButton, NSWindowZoomButton):
            btn = panel.standardWindowButton_(kind)
            if btn is not None:
                btn.setHidden_(True)

        root = DropView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        root.on_hover = self._drop_hover
        root.on_files = lambda paths: self.on_files and self.on_files(paths)
        self.root = root
        root.setMaterial_(MATERIAL_POPOVER)
        root.setBlendingMode_(BLEND_BEHIND_WINDOW)
        root.setState_(STATE_ACTIVE)
        panel.setContentView_(root)
        root.addSubview_(theme.surface(root.bounds()))

        # Marke: kleines S mit Welle und Name, zentriert in der Titelleiste
        brand = NSView.alloc().initWithFrame_(NSMakeRect((WIDTH - 76) / 2.0, HEIGHT - 22.0, 76, 16))
        brand.addSubview_(theme.BrandMark.alloc().initWithFrame_(NSMakeRect(0, 0, 16, 16)))
        name = _label("SBeach", 12.0, theme.SEMIBOLD, NSColor.secondaryLabelColor(),
                      NSMakeRect(20, -1, 56, 17), centered=False)
        brand.addSubview_(name)
        root.addSubview_(brand)

        # Aufnahmeknopf
        self.button = RecordButton.alloc().initWithFrame_(NSMakeRect((WIDTH - 96) / 2.0, 172, 96, 96))
        self.button.on_press = self._pressed
        root.addSubview_(self.button)

        # Equalizer
        self.eq = EqualizerView.alloc().initWithFrame_(NSMakeRect((WIDTH - 168) / 2.0, 134, 168, 26))
        self.eq.configure(24, 3.0)
        root.addSubview_(self.eq)

        # Status
        self.title = _label("Bereit", 17.0, theme.SEMIBOLD, NSColor.labelColor(),
                            NSMakeRect(24, 90, WIDTH - 48, 22))
        root.addSubview_(self.title)
        self.subtitle = _label("", 12.0, theme.REGULAR, NSColor.secondaryLabelColor(),
                               NSMakeRect(24, 69, WIDTH - 48, 17))
        self.subtitle.setFont_(theme.mono_digits(12.0))
        root.addSubview_(self.subtitle)

        # Feine Trennlinie und Fußzeile mit aktivem Modus
        line = NSBox.alloc().initWithFrame_(NSMakeRect(16, 48, WIDTH - 32, 1))
        line.setBoxType_(NSBoxCustom)
        line.setBorderWidth_(0)
        line.setFillColor_(theme.color("hairline"))
        root.addSubview_(line)

        self.mode_button = _plain_button("", self, "openSettings:", NSMakeRect(12, 14, 220, 22),
                                         NSColor.secondaryLabelColor())
        self.mode_button.setAlignment_(0)
        self.mode_button.setToolTip_("Erkennungsmodus ändern")
        root.addSubview_(self.mode_button)

        gear = theme.symbol("slider.horizontal.3", "Einstellungen", 13.0)
        self.gear = NSButton.buttonWithImage_target_action_(gear, self, "openSettings:")
        self.gear.setBordered_(False)
        self.gear.setFrame_(NSMakeRect(WIDTH - 16 - 24, 13, 24, 24))
        self.gear.setContentTintColor_(NSColor.secondaryLabelColor())
        self.gear.setToolTip_("Einstellungen")
        root.addSubview_(self.gear)

        add = theme.symbol("waveform.badge.plus", "Datei transkribieren", 13.0) or theme.symbol(
            "doc.badge.plus", "Datei transkribieren", 13.0)
        self.file_btn = NSButton.buttonWithImage_target_action_(add, self, "openFile:")
        self.file_btn.setBordered_(False)
        self.file_btn.setFrame_(NSMakeRect(WIDTH - 16 - 24 - 28, 13, 24, 24))
        self.file_btn.setContentTintColor_(NSColor.secondaryLabelColor())
        self.file_btn.setToolTip_("Audio oder Video transkribieren (oder Datei hierher ziehen)")
        root.addSubview_(self.file_btn)

        self.ring = _DropRing.alloc().initWithFrame_(root.bounds())
        self.ring.setHidden_(True)
        root.addSubview_(self.ring)

        self.panel = panel
        panel.setFrameAutosaveName_("SBeachMainWindow")
        if not panel.setFrameUsingName_("SBeachMainWindow"):
            panel.center()

    # Sichtbarkeit -------------------------------------------------------
    @objc.python_method
    def visible(self) -> bool:
        return bool(self.panel.isVisible())

    @objc.python_method
    def show(self) -> None:
        self.panel.orderFrontRegardless()

    @objc.python_method
    def toggle(self) -> None:
        if self.visible():
            self.panel.orderOut_(None)
        else:
            self.show()

    def windowShouldClose_(self, sender):
        self.panel.orderOut_(None)
        return False

    # Aktionen -----------------------------------------------------------
    @objc.python_method
    def _pressed(self) -> None:
        if self.on_record is not None:
            self.on_record()

    def openFile_(self, sender):
        if self.on_open_file is not None:
            self.on_open_file()

    @objc.python_method
    def _drop_hover(self, active: bool) -> None:
        self.dropping = active
        self.ring.setHidden_(not active)
        self._render_subtitle()

    def openSettings_(self, sender):
        if self.on_settings is not None:
            self.on_settings()

    # Darstellung --------------------------------------------------------
    @objc.python_method
    def render(self, state: dict) -> None:
        self.state = state
        recording = state["recording"]
        busy = state["pending"] > 0
        self.button.set_recording(recording)
        self.button.set_enabled(state["status"] != "error" or recording)
        self.eq.set_mode("recording" if recording else ("transcribing" if busy else "idle"))

        if recording:
            title, color = "Hört zu", theme.color("sea")
        elif busy:
            title, color = "Schreibt", NSColor.labelColor()
        elif state["status"] == "loading":
            title, color = "Wird vorbereitet", NSColor.labelColor()
        elif state["status"] == "error":
            title, color = "Nicht bereit", NSColor.labelColor()
        else:
            title, color = "Bereit", NSColor.labelColor()
        self.title.setStringValue_(title)
        self.title.setTextColor_(color)
        self._render_subtitle()

        _set_button_title(self.mode_button, state["mode_label"], NSColor.secondaryLabelColor())

        if recording:
            theme.animator().add(("clock", id(self)), self._tick)

    @objc.python_method
    def _tick(self, dt: float):
        self._render_subtitle()
        return bool(self.state.get("recording"))

    @objc.python_method
    def _render_subtitle(self) -> None:
        s = self.state
        if self.dropping:
            text = "Loslassen zum Transkribieren"
        elif s.get("recording"):
            secs = int(self.elapsed()) if self.elapsed else 0
            text = f"{secs // 60}:{secs % 60:02d}   ·   Esc bricht ab"
        elif s.get("pending"):
            text = "Einen Moment"
        elif time.monotonic() < self.note_until:
            text = self.note_text
        elif s.get("status") == "loading":
            text = s.get("loading_hint", "Sprachmodell wird geladen")
        elif s.get("status") == "error":
            text = s.get("detail") or "Details unter Einstellungen"
        else:
            text = s.get("hint", "")
        if self.subtitle.stringValue() != text:
            self.subtitle.setStringValue_(text)

    @objc.python_method
    def note(self, text: str, seconds: float = 3.0) -> None:
        self.note_text = text
        self.note_until = time.monotonic() + seconds
        self._render_subtitle()
        AppHelper.callLater(seconds + 0.05, self._render_subtitle)
