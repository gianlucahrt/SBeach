"""Ergebnisfenster für transkribierte Dateien.

Aufbau von oben nach unten: Dateiname mit Metadaten und Exportknöpfen, der
Fortschritt während der Transkription, das Transkript (editierbar), darunter
„Mit KI weiterarbeiten“ mit Vorschlägen als Kapseln, einem freien Prompt und
dem Ergebnis, das live einläuft.
"""

from __future__ import annotations

import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSButton,
    NSColor,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSImageView,
    NSLayoutConstraint,
    NSMenuItem,
    NSModalResponseOK,
    NSPasteboard,
    NSPasteboardTypeString,
    NSPopUpButton,
    NSProgressIndicator,
    NSSavePanel,
    NSStackView,
    NSString,
    NSTextField,
    NSTextView,
    NSTrackingActiveAlways,
    NSTrackingArea,
    NSTrackingInVisibleRect,
    NSTrackingMouseEnteredAndExited,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSUserInterfaceLayoutOrientationVertical,
    NSView,
    NSVisualEffectView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSInsetRect, NSMakePoint, NSMakeRect, NSMakeSize, NSObject, NSURL

from ..llm import PRESETS
from . import theme

WIDTH, HEIGHT = 640.0, 780.0
GRAVITY_LEADING, GRAVITY_TRAILING = 1, 3
ALIGN_LEADING, ALIGN_CENTER_Y, ALIGN_WIDTH = 5, 10, 7


class Chip(NSView):
    """Kapsel Knopf für Prompt Vorschläge."""

    def initWithTitle_(self, title):
        self = objc.super(Chip, self).initWithFrame_(NSMakeRect(0, 0, 10, 28))
        if self is None:
            return None
        self.title = title
        self.on_press = None
        self.enabled = True
        self.hover = False
        self.pressed = False
        self._tracking = None
        self.setAccessibilityLabel_(title)
        return self

    @objc.python_method
    def _attrs(self):
        return {NSFontAttributeName: theme.font(12.0, theme.MEDIUM),
                NSForegroundColorAttributeName: NSColor.labelColor()}

    def intrinsicContentSize(self):
        size = NSString.stringWithString_(self.title).sizeWithAttributes_(self._attrs())
        return NSMakeSize(size.width + 28.0, 28.0)

    def isOpaque(self):
        return False

    def viewDidChangeEffectiveAppearance(self):
        self.setNeedsDisplay_(True)

    @objc.python_method
    def set_enabled(self, enabled):
        self.enabled = enabled
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        b = NSInsetRect(self.bounds(), 0.5, 0.5)
        r = b.size.height / 2.0
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, r, r)
        alpha = 1.0 if self.enabled else 0.45
        fill = theme.color("face_hover") if (self.hover and self.enabled) else theme.color("face")
        fill.colorWithAlphaComponent_(alpha).set()
        path.fill()
        (theme.color("sea") if (self.pressed and self.enabled) else theme.color("ring")).set()
        path.setLineWidth_(1.0)
        path.stroke()
        attrs = self._attrs()
        if not self.enabled:
            attrs[NSForegroundColorAttributeName] = NSColor.tertiaryLabelColor()
        s = NSString.stringWithString_(self.title)
        size = s.sizeWithAttributes_(attrs)
        s.drawAtPoint_withAttributes_(
            NSMakePoint((self.bounds().size.width - size.width) / 2.0,
                        (self.bounds().size.height - size.height) / 2.0), attrs)

    def updateTrackingAreas(self):
        if self._tracking is not None:
            self.removeTrackingArea_(self._tracking)
        self._tracking = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways | NSTrackingInVisibleRect,
            self, None)
        self.addTrackingArea_(self._tracking)
        objc.super(Chip, self).updateTrackingAreas()

    def mouseEntered_(self, e):
        self.hover = True
        self.setNeedsDisplay_(True)

    def mouseExited_(self, e):
        self.hover = False
        self.pressed = False
        self.setNeedsDisplay_(True)

    def mouseDown_(self, e):
        if self.enabled:
            self.pressed = True
            self.setNeedsDisplay_(True)

    def mouseUp_(self, e):
        was, self.pressed = self.pressed, False
        self.setNeedsDisplay_(True)
        if was and self.enabled and self.on_press is not None:
            self.on_press()

    def isAccessibilityElement(self):
        return True

    def accessibilityRole(self):
        return "AXButton"

    def accessibilityPerformPress(self):
        if self.enabled and self.on_press is not None:
            self.on_press()
        return True


class _Card(NSView):
    """Abgerundete Fläche mit feiner Kontur, Hintergrund für Textbereiche."""

    def isOpaque(self):
        return False

    def viewDidChangeEffectiveAppearance(self):
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        b = NSInsetRect(self.bounds(), 0.5, 0.5)
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, 10.0, 10.0)
        theme.color("face").colorWithAlphaComponent_(0.92).set()
        path.fill()
        theme.color("hairline").set()
        path.setLineWidth_(1.0)
        path.stroke()


def _label(text, size, weight, color):
    f = NSTextField.labelWithString_(text)
    f.setFont_(theme.font(size, weight))
    f.setTextColor_(color)
    f.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return f


def _icon_button(symbol, description, target, action, size=14.0):
    b = NSButton.buttonWithImage_target_action_(theme.symbol(symbol, description, size), target, action)
    b.setBordered_(False)
    b.setContentTintColor_(NSColor.secondaryLabelColor())
    b.setToolTip_(description)
    b.setTranslatesAutoresizingMaskIntoConstraints_(False)
    b.widthAnchor().constraintEqualToConstant_(26).setActive_(True)
    b.heightAnchor().constraintEqualToConstant_(26).setActive_(True)
    return b


def _text_area(editable: bool):
    scroll = NSTextView.scrollableTextView()
    scroll.setDrawsBackground_(False)
    scroll.setBorderType_(0)
    scroll.setAutohidesScrollers_(True)
    tv = scroll.documentView()
    tv.setDrawsBackground_(False)
    tv.setEditable_(editable)
    tv.setSelectable_(True)
    tv.setRichText_(False)
    tv.setFont_(theme.font(13.5))
    tv.setTextColor_(NSColor.labelColor())
    tv.setTextContainerInset_(NSMakeSize(14, 12))
    tv.setAutomaticQuoteSubstitutionEnabled_(False)
    tv.setAutomaticDashSubstitutionEnabled_(False)
    card = _Card.alloc().initWithFrame_(NSMakeRect(0, 0, 100, 100))
    card.setTranslatesAutoresizingMaskIntoConstraints_(False)
    scroll.setTranslatesAutoresizingMaskIntoConstraints_(False)
    card.addSubview_(scroll)
    for a, b in ((scroll.leadingAnchor(), card.leadingAnchor()), (scroll.trailingAnchor(), card.trailingAnchor()),
                 (scroll.topAnchor(), card.topAnchor()), (scroll.bottomAnchor(), card.bottomAnchor())):
        a.constraintEqualToAnchor_constant_(b, 0).setActive_(True)
    return card, tv


def _hstack(views, spacing=8.0):
    s = NSStackView.stackViewWithViews_(views)
    s.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
    s.setSpacing_(spacing)
    s.setAlignment_(ALIGN_CENTER_Y)
    s.setTranslatesAutoresizingMaskIntoConstraints_(False)
    return s


class ResultWindow(NSObject):
    def initWithPath_(self, path):
        self = objc.super(ResultWindow, self).init()
        if self is None:
            return None
        self.path = str(path)
        self.on_prompt = None   # callable(instruction, label)
        self.on_close = None
        self.segments = []
        self.busy_ai = False
        self.ready = False
        self.provider_label = ""
        self._build()
        return self

    # Aufbau ---------------------------------------------------------------
    @objc.python_method
    def _build(self):
        from pathlib import Path

        name = Path(self.path).name
        style = (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskMiniaturizable
                 | NSWindowStyleMaskResizable | NSWindowStyleMaskFullSizeContentView)
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, HEIGHT), style, NSBackingStoreBuffered, False)
        win.setTitle_(name)
        win.setTitlebarAppearsTransparent_(True)
        win.setReleasedWhenClosed_(False)
        win.setMinSize_(NSMakeSize(520, 600))
        win.setDelegate_(self)
        win.setTabbingMode_(2)

        root = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        root.setMaterial_(21)  # Fensterhintergrund
        root.setBlendingMode_(0)
        root.setState_(1)
        win.setContentView_(root)
        root.addSubview_(theme.surface(root.bounds()))

        # Kopfzeile
        is_video = Path(self.path).suffix.lower().lstrip(".") in {"mp4", "mov", "m4v", "mkv", "avi", "3gp"}
        icon = NSImageView.imageViewWithImage_(
            theme.symbol("film" if is_video else "waveform", "Datei", 18.0, theme.MEDIUM))
        icon.setContentTintColor_(theme.color("sea"))
        icon.setTranslatesAutoresizingMaskIntoConstraints_(False)
        icon.widthAnchor().constraintEqualToConstant_(28).setActive_(True)
        self.title = _label(name, 15.0, theme.SEMIBOLD, NSColor.labelColor())
        self.title.cell().setLineBreakMode_(5)
        self.title.setContentCompressionResistancePriority_forOrientation_(250, 0)
        self.meta = _label("Wird gelesen", 12.0, theme.REGULAR, NSColor.secondaryLabelColor())
        names = NSStackView.stackViewWithViews_([self.title, self.meta])
        names.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        names.setAlignment_(ALIGN_LEADING)
        names.setSpacing_(2.0)

        self.copy_btn = _icon_button("doc.on.doc", "Transkript kopieren", self, "copyTranscript:")
        self.export_btn = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 40, 26), True)
        self.export_btn.setBordered_(False)
        self.export_btn.setTranslatesAutoresizingMaskIntoConstraints_(False)
        menu = self.export_btn.menu()
        head = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("", None, "")
        head.setImage_(theme.symbol("square.and.arrow.down", "Exportieren", 14.0))
        menu.addItem_(head)
        for title, action in (("Als Text sichern …", "exportText:"), ("Als Untertitel (SRT) sichern …", "exportSrt:")):
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, "")
            item.setTarget_(self)
            menu.addItem_(item)
        self.export_btn.setToolTip_("Exportieren")
        self.export_btn.cell().setArrowPosition_(0)
        self.export_btn.setContentTintColor_(NSColor.secondaryLabelColor())
        spacer = NSView.alloc().init()
        spacer.setContentHuggingPriority_forOrientation_(1, 0)
        header = _hstack([icon, names, spacer, self.copy_btn, self.export_btn], 10.0)

        # Fortschritt
        self.progress = NSProgressIndicator.alloc().init()
        self.progress.setStyle_(0)
        self.progress.setIndeterminate_(True)
        self.progress.setControlSize_(1)
        self.progress.setMinValue_(0.0)
        self.progress.setMaxValue_(1.0)
        self.progress.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.progress.startAnimation_(None)

        # Transkript
        self.transcript_card, self.transcript = _text_area(editable=True)
        self.transcript.setString_("")
        self.placeholder = _label("Das Transkript erscheint hier, sobald die Datei verarbeitet ist.",
                                  13.0, theme.REGULAR, NSColor.tertiaryLabelColor())
        self.transcript_card.addSubview_(self.placeholder)
        self.placeholder.centerXAnchor().constraintEqualToAnchor_(self.transcript_card.centerXAnchor()).setActive_(True)
        self.placeholder.centerYAnchor().constraintEqualToAnchor_(self.transcript_card.centerYAnchor()).setActive_(True)

        # KI Bereich
        self.ai_title = _label("Mit KI weiterarbeiten", 12.0, theme.SEMIBOLD, NSColor.secondaryLabelColor())
        self.provider = _label("", 11.0, theme.MEDIUM, NSColor.secondaryLabelColor())
        sp2 = NSView.alloc().init()
        sp2.setContentHuggingPriority_forOrientation_(1, 0)
        ai_head = _hstack([self.ai_title, sp2, self.provider])

        self.chips = []
        for preset in PRESETS:
            chip = Chip.alloc().initWithTitle_(preset.label)
            chip.setTranslatesAutoresizingMaskIntoConstraints_(False)
            chip.on_press = (lambda p=preset: self._send(p.instruction, p.label))
            self.chips.append(chip)
        chip_row = _hstack(self.chips, 8.0)

        self.prompt = NSTextField.textFieldWithString_("")
        self.prompt.setPlaceholderString_("Eigene Anweisung, z. B. Was sind die Kernaussagen?")
        self.prompt.setBezelStyle_(1)
        self.prompt.setFont_(theme.font(13.0))
        self.prompt.setTarget_(self)
        self.prompt.setAction_("sendPrompt:")
        self.prompt.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.send_btn = NSButton.buttonWithImage_target_action_(
            theme.symbol("arrow.up.circle.fill", "Senden", 22.0), self, "sendPrompt:")
        self.send_btn.setBordered_(False)
        self.send_btn.setContentTintColor_(theme.color("sea"))
        self.send_btn.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.send_btn.setToolTip_("Senden")
        prompt_row = _hstack([self.prompt, self.send_btn], 8.0)

        self.output_title = _label("Ergebnis", 12.0, theme.SEMIBOLD, NSColor.secondaryLabelColor())
        self.output_state = _label("", 11.0, theme.MEDIUM, NSColor.secondaryLabelColor())
        self.copy_out = _icon_button("doc.on.doc", "Ergebnis kopieren", self, "copyOutput:")
        sp3 = NSView.alloc().init()
        sp3.setContentHuggingPriority_forOrientation_(1, 0)
        self.output_head = _hstack([self.output_title, self.output_state, sp3, self.copy_out])
        self.output_card, self.output = _text_area(editable=False)

        stack = NSStackView.stackViewWithViews_([
            header, self.progress, self.transcript_card, ai_head, chip_row, prompt_row,
            self.output_head, self.output_card])
        stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        stack.setAlignment_(ALIGN_LEADING)
        stack.setSpacing_(theme.M)
        stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        stack.setCustomSpacing_afterView_(theme.L, header)
        stack.setCustomSpacing_afterView_(theme.XL, self.transcript_card)
        stack.setCustomSpacing_afterView_(theme.S, ai_head)
        stack.setCustomSpacing_afterView_(theme.XL, prompt_row)
        stack.setCustomSpacing_afterView_(theme.S, self.output_head)
        root.addSubview_(stack)
        for v in (header, self.progress, self.transcript_card, ai_head, prompt_row, self.output_head,
                  self.output_card):
            v.widthAnchor().constraintEqualToAnchor_(stack.widthAnchor()).setActive_(True)

        NSLayoutConstraint.activateConstraints_([
            stack.leadingAnchor().constraintEqualToAnchor_constant_(root.leadingAnchor(), theme.XL),
            root.trailingAnchor().constraintEqualToAnchor_constant_(stack.trailingAnchor(), theme.XL),
            stack.topAnchor().constraintEqualToAnchor_constant_(root.topAnchor(), 40.0),
            root.bottomAnchor().constraintEqualToAnchor_constant_(stack.bottomAnchor(), theme.XL),
            self.transcript_card.heightAnchor().constraintGreaterThanOrEqualToConstant_(150.0),
            self.output_card.heightAnchor().constraintGreaterThanOrEqualToConstant_(120.0),
            self.output_card.heightAnchor().constraintEqualToAnchor_multiplier_(self.transcript_card.heightAnchor(), 0.8),
        ])
        for v in (self.transcript_card, self.output_card):
            v.setContentHuggingPriority_forOrientation_(1, 1)

        self.window = win
        self._set_ai_enabled(False)
        self._show_output(False)
        win.center()

    # Anzeige ----------------------------------------------------------------
    @objc.python_method
    def show(self):
        NSApp.activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)

    @objc.python_method
    def set_provider(self, label: str):
        self.provider_label = label
        self.provider.setStringValue_(label)

    @objc.python_method
    def set_progress(self, fraction: float | None, text: str):
        self.progress.setHidden_(False)
        if fraction is None:
            self.progress.setIndeterminate_(True)
            self.progress.startAnimation_(None)
        else:
            self.progress.setIndeterminate_(False)
            self.progress.setDoubleValue_(max(0.02, fraction))
        self.meta.setStringValue_(text)

    @objc.python_method
    def set_transcript(self, text: str, segments, meta: str):
        self.segments = list(segments)
        self.placeholder.setHidden_(True)
        self.transcript.setString_(text or "Keine Sprache erkannt.")
        self.meta.setStringValue_(meta)
        self.progress.stopAnimation_(None)
        self.progress.setHidden_(True)
        self.ready = bool(text)
        self._set_ai_enabled(self.ready)
        if self.ready:
            self.window.makeFirstResponder_(self.prompt)

    @objc.python_method
    def set_error(self, message: str):
        self.progress.stopAnimation_(None)
        self.progress.setHidden_(True)
        self.meta.setStringValue_("Fehler beim Lesen")
        self.meta.setTextColor_(NSColor.systemRedColor())
        self.placeholder.setHidden_(True)
        self.transcript.setString_(message)

    @objc.python_method
    def ai_started(self, label: str):
        self.busy_ai = True
        self._set_ai_enabled(False)
        self._show_output(True)
        self.output_title.setStringValue_(label)
        self.output_state.setStringValue_(f"{self.provider_label} schreibt …")
        self.output.setString_("")

    @objc.python_method
    def ai_update(self, text: str):
        self.output.setString_(text)
        self.output.scrollToEndOfDocument_(None)

    @objc.python_method
    def ai_done(self, text: str | None = None, error: str | None = None):
        self.busy_ai = False
        self._set_ai_enabled(self.ready)
        if error:
            self.output_state.setStringValue_("")
            self.output.setString_(error)
            self.output.setTextColor_(NSColor.systemRedColor())
        else:
            if text is not None:
                self.output.setString_(text)
            self.output.setTextColor_(NSColor.labelColor())
            self.output_state.setStringValue_(self.provider_label)
            self.output.scrollToBeginningOfDocument_(None)

    @objc.python_method
    def _show_output(self, visible: bool):
        self.output_head.setHidden_(not visible)
        self.output_card.setHidden_(not visible)

    @objc.python_method
    def _set_ai_enabled(self, enabled: bool):
        for chip in self.chips:
            chip.set_enabled(enabled)
        self.prompt.setEnabled_(enabled)
        self.send_btn.setEnabled_(enabled)

    # Aktionen ---------------------------------------------------------------
    @objc.python_method
    def _send(self, instruction: str, label: str):
        if not self.ready or self.busy_ai or not instruction.strip():
            return
        if self.on_prompt is not None:
            self.on_prompt(self, instruction, label, str(self.transcript.string()))

    def sendPrompt_(self, sender):
        text = str(self.prompt.stringValue()).strip()
        if text:
            self._send(text, "Ergebnis")

    @objc.python_method
    def _copy(self, text: str):
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)

    def copyTranscript_(self, sender):
        self._copy(str(self.transcript.string()))

    def copyOutput_(self, sender):
        self._copy(str(self.output.string()))

    @objc.python_method
    def _save(self, suffix: str, content: str):
        from pathlib import Path

        panel = NSSavePanel.savePanel()
        p = Path(self.path)
        panel.setNameFieldStringValue_(p.stem + suffix)
        panel.setDirectoryURL_(NSURL.fileURLWithPath_(str(p.parent)))
        if panel.runModal() == NSModalResponseOK:
            Path(str(panel.URL().path())).write_text(content, encoding="utf-8")

    def exportText_(self, sender):
        self._save(".txt", str(self.transcript.string()))

    def exportSrt_(self, sender):
        from ..media import to_srt

        self._save(".srt", to_srt(self.segments))

    def windowWillClose_(self, note):
        if self.on_close is not None:
            self.on_close(self)

