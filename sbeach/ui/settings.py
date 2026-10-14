"""Einstellungsfenster im Stil der macOS Systemeinstellungen.

Ein ruhiges, zweispaltiges Raster: Beschriftung rechtsbündig, Steuerelemente
linksbündig. Änderungen wirken sofort, es gibt keinen Speichern Knopf.
"""

from __future__ import annotations

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBox,
    NSBoxSeparator,
    NSButton,
    NSColor,
    NSGridCell,
    NSGridView,
    NSPopUpButton,
    NSSegmentedControl,
    NSSegmentStyleAutomatic,
    NSStackView,
    NSTextField,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSView,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSMakeRect, NSObject

from ..hotkey import HOTKEYS
from ..llm import CLAUDE_MODELS
from ..transcriber import LANGUAGE_LABELS, MODELS
from . import theme

PLACEMENT_TRAILING = 3
PLACEMENT_LEADING = 2
CONTROL_SMALL = 1
SWITCH_BUTTON = 3  # NSButtonTypeSwitch
MODEL_KEYS = ["fast", "balanced", "precise"]
MODE_KEYS = ["hold", "toggle"]
CONTROL_WIDTH = 232.0


def _label(text: str, secondary: bool = False):
    field = NSTextField.labelWithString_(text)
    field.setFont_(theme.font(13.0))
    field.setTextColor_(NSColor.secondaryLabelColor() if secondary else NSColor.labelColor())
    return field


def _caption(text: str):
    field = NSTextField.wrappingLabelWithString_(text)
    field.setFont_(theme.font(11.0))
    field.setTextColor_(NSColor.secondaryLabelColor())
    field.setPreferredMaxLayoutWidth_(CONTROL_WIDTH + 96)
    return field


class SettingsWindow(NSObject):
    def init(self):
        self = objc.super(SettingsWindow, self).init()
        if self is None:
            return None
        self.window = None
        self.cfg = None
        self.on_change = None          # callable(key, value)
        self.devices = lambda: []      # callable() -> [(index, name)]
        self.permissions = lambda: []  # callable() -> [(name, granted, open_fn)]
        self.login_state = None        # callable() -> bool | None (None = nicht verfügbar)
        self.has_api_key = lambda: False
        self._perm_actions = {}
        return self

    # Öffentliche API ----------------------------------------------------
    @objc.python_method
    def show(self, cfg) -> None:
        from AppKit import NSApp

        self.cfg = cfg
        self._build()
        NSApp.activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)

    # Aufbau -------------------------------------------------------------
    @objc.python_method
    def _build(self) -> None:
        cfg = self.cfg
        if self.window is None:
            win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, 480, 400), NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
                NSBackingStoreBuffered, False)
            win.setTitle_("SBeach Einstellungen")
            win.setReleasedWhenClosed_(False)
            self.window = win
            win.center()

        rows = []

        self.hotkey = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 200, 26), False)
        for key, (label, short, *_rest) in HOTKEYS.items():
            self.hotkey.addItemWithTitle_(f"{label}")
            self.hotkey.lastItem().setRepresentedObject_(key)
        self._select_obj(self.hotkey, cfg["hotkey"])
        self.hotkey.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
        self.hotkey.setTarget_(self)
        self.hotkey.setAction_("changeHotkey:")
        rows.append(("Kurzbefehl", self.hotkey))

        self.mode = NSSegmentedControl.segmentedControlWithLabels_trackingMode_target_action_(
            ["Halten", "Umschalten"], 0, self, "changeMode:")
        self.mode.setSegmentStyle_(NSSegmentStyleAutomatic)
        self.mode.setSelectedSegment_(MODE_KEYS.index(cfg["mode"]))
        rows.append(("Auslösen", self.mode))
        rows.append(("", _caption("Halten: sprechen, solange die Taste gedrückt ist.\n"
                                  "Umschalten: drücken startet, erneut drücken fügt ein.")))

        self.language = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 200, 26), False)
        for key, label in LANGUAGE_LABELS.items():
            self.language.addItemWithTitle_(label)
            self.language.lastItem().setRepresentedObject_(key)
        self._select_obj(self.language, cfg["language"])
        self.language.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
        self.language.setTarget_(self)
        self.language.setAction_("changeLanguage:")
        rows.append(("Sprache", self.language))

        self.model = NSSegmentedControl.segmentedControlWithLabels_trackingMode_target_action_(
            [MODELS[k]["label"] for k in MODEL_KEYS], 0, self, "changeModel:")
        self.model.setSelectedSegment_(MODEL_KEYS.index(cfg["model"]))
        for i, k in enumerate(MODEL_KEYS):
            self.model.setToolTip_forSegment_(MODELS[k]["hint"], i)
        self.model.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
        self.mode.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
        rows.append(("Genauigkeit", self.model))

        self.device = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 200, 26), False)
        self.device.addItemWithTitle_("Systemstandard")
        self.device.lastItem().setRepresentedObject_(-1)
        try:
            for idx, name in self.devices():
                self.device.addItemWithTitle_(name)
                self.device.lastItem().setRepresentedObject_(idx)
        except Exception:
            pass
        self._select_obj(self.device, -1 if cfg["input_device"] is None else cfg["input_device"])
        self.device.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
        self.device.setTarget_(self)
        self.device.setAction_("changeDevice:")
        rows.append(("Mikrofon", self.device))

        self.insert = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 200, 26), False)
        for key, label in (("paste", "Einfügen (empfohlen)"), ("type", "Tippen simulieren")):
            self.insert.addItemWithTitle_(label)
            self.insert.lastItem().setRepresentedObject_(key)
        self._select_obj(self.insert, cfg["insert_method"])
        self.insert.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
        self.insert.setTarget_(self)
        self.insert.setAction_("changeInsert:")
        rows.append(("Text eingeben", self.insert))

        self.vocab = NSTextField.textFieldWithString_(", ".join(cfg["vocabulary"]))
        self.vocab.setPlaceholderString_("z. B. Saxion, Hyrox, SBeach")
        self.vocab.setBezelStyle_(1)  # abgerundet wie in den Systemeinstellungen
        self.vocab.setFont_(theme.font(13.0))
        self.vocab.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
        self.vocab.cell().setSendsActionOnEndEditing_(True)
        self.vocab.setTarget_(self)
        self.vocab.setAction_("changeVocabulary:")
        rows.append(("Eigene Begriffe", self.vocab))

        self.sounds = self._switch("Töne bei Start und Ende", cfg["sounds"], "changeSounds:")
        rows.append(("Allgemein", self.sounds))
        self.restore = self._switch("Zwischenablage danach wiederherstellen", cfg["restore_clipboard"],
                                    "changeRestore:")
        rows.append(("", self.restore))
        login = self.login_state() if self.login_state else None
        if login is not None:
            self.login = self._switch("Beim Anmelden öffnen", login, "changeLogin:")
            rows.append(("", self.login))

        rows.append(("SEPARATOR", None))

        # KI ---------------------------------------------------------------
        self.ai = NSSegmentedControl.segmentedControlWithLabels_trackingMode_target_action_(
            ["Lokal", "Claude"], 0, self, "changeProvider:")
        self.ai.setSelectedSegment_(0 if cfg["ai_provider"] == "local" else 1)
        self.ai.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
        rows.append(("KI", self.ai))
        if cfg["ai_provider"] == "local":
            rows.append(("", _caption("Läuft vollständig auf diesem Mac. Beim ersten Einsatz wird "
                                      "das Sprachmodell einmalig geladen (etwa 4 GB).")))
        else:
            self.claude_model = NSPopUpButton.alloc().initWithFrame_pullsDown_(NSMakeRect(0, 0, 200, 26), False)
            for key, label in CLAUDE_MODELS.items():
                self.claude_model.addItemWithTitle_(label)
                self.claude_model.lastItem().setRepresentedObject_(key)
            self._select_obj(self.claude_model, cfg["claude_model"])
            self.claude_model.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
            self.claude_model.setTarget_(self)
            self.claude_model.setAction_("changeClaudeModel:")
            rows.append(("Modell", self.claude_model))
            from AppKit import NSSecureTextField

            self.api_key = NSSecureTextField.alloc().initWithFrame_(NSMakeRect(0, 0, CONTROL_WIDTH, 22))
            self.api_key.setBezelStyle_(1)
            self.api_key.setFont_(theme.font(13.0))
            has_key = bool(self.has_api_key())
            self.api_key.setPlaceholderString_("Gespeichert im Schlüsselbund" if has_key else "API Schlüssel einfügen")
            self.api_key.widthAnchor().constraintEqualToConstant_(CONTROL_WIDTH).setActive_(True)
            self.api_key.cell().setSendsActionOnEndEditing_(True)
            self.api_key.setTarget_(self)
            self.api_key.setAction_("changeApiKey:")
            rows.append(("API Schlüssel", self.api_key))
            rows.append(("", _caption("Nur der Text geht an Claude, die Spracherkennung bleibt lokal. "
                                      "Schlüssel unter console.anthropic.com erstellen.")))

        rows.append(("SEPARATOR", None))
        self._perm_actions = {}
        for i, (name, granted, open_fn) in enumerate(self.permissions()):
            rows.append(("Berechtigungen" if i == 0 else "", self._permission_row(name, granted, open_fn, i)))

        grid = NSGridView.gridViewWithNumberOfColumns_rows_(2, 0)
        grid.setRowSpacing_(10.0)
        grid.setColumnSpacing_(12.0)
        grid.setRowAlignment_(2)  # erste Grundlinie, Beschriftung und Wert auf einer Linie
        for title, control in rows:
            if title == "SEPARATOR":
                box = NSBox.alloc().initWithFrame_(NSMakeRect(0, 0, 400, 1))
                box.setBoxType_(NSBoxSeparator)
                row = grid.addRowWithViews_([box, NSGridCell.emptyContentView()])
                row.mergeCellsInRange_((0, 2))
                row.setTopPadding_(6.0)
                row.setBottomPadding_(6.0)
                continue
            label = _label(title) if title else NSGridCell.emptyContentView()
            row = grid.addRowWithViews_([label, control])
        grid.columnAtIndex_(0).setXPlacement_(PLACEMENT_TRAILING)
        grid.columnAtIndex_(1).setXPlacement_(PLACEMENT_LEADING)
        grid.setTranslatesAutoresizingMaskIntoConstraints_(False)

        content = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, 480, 400))
        content.addSubview_(grid)
        for a, b, c in (
            (grid.leadingAnchor(), content.leadingAnchor(), 28.0),
            (grid.topAnchor(), content.topAnchor(), 24.0),
        ):
            a.constraintEqualToAnchor_constant_(b, c).setActive_(True)
        content.trailingAnchor().constraintEqualToAnchor_constant_(grid.trailingAnchor(), 28.0).setActive_(True)
        content.bottomAnchor().constraintEqualToAnchor_constant_(grid.bottomAnchor(), 24.0).setActive_(True)
        self.window.setContentView_(content)
        content.layoutSubtreeIfNeeded()
        self.window.setContentSize_(content.fittingSize())

    @objc.python_method
    def _switch(self, title: str, value: bool, action: str):
        button = NSButton.checkboxWithTitle_target_action_(title, self, action)
        button.setState_(1 if value else 0)
        return button

    @objc.python_method
    def _permission_row(self, name: str, granted: bool, open_fn, index: int):
        dot = NSTextField.labelWithString_("●")
        dot.setFont_(theme.font(9.0))
        dot.setTextColor_(NSColor.systemGreenColor() if granted else NSColor.systemOrangeColor())
        state = _label("erlaubt" if granted else "fehlt", secondary=True)
        views = [dot, _label(name), state]
        if not granted:
            button = NSButton.buttonWithTitle_target_action_("Freigeben…", self, "openPermission:")
            button.setControlSize_(CONTROL_SMALL)
            button.setTag_(index)
            self._perm_actions[index] = open_fn
            views.append(button)
        stack = NSStackView.stackViewWithViews_(views)
        stack.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        stack.setSpacing_(6.0)
        return stack

    @staticmethod
    def _select_obj(popup, value):
        for item in popup.itemArray():
            if item.representedObject() == value:
                popup.selectItem_(item)
                return

    @objc.python_method
    def _emit(self, key, value):
        if self.on_change is not None:
            self.on_change(key, value)

    # Aktionen -----------------------------------------------------------
    def changeHotkey_(self, sender):
        self._emit("hotkey", sender.selectedItem().representedObject())

    def changeMode_(self, sender):
        self._emit("mode", MODE_KEYS[sender.selectedSegment()])

    def changeLanguage_(self, sender):
        self._emit("language", sender.selectedItem().representedObject())

    def changeModel_(self, sender):
        self._emit("model", MODEL_KEYS[sender.selectedSegment()])

    def changeDevice_(self, sender):
        idx = sender.selectedItem().representedObject()
        self._emit("input_device", None if idx == -1 else int(idx))

    def changeInsert_(self, sender):
        self._emit("insert_method", sender.selectedItem().representedObject())

    def changeVocabulary_(self, sender):
        words = [w.strip() for w in str(sender.stringValue()).split(",") if w.strip()]
        self._emit("vocabulary", words)

    def changeSounds_(self, sender):
        self._emit("sounds", bool(sender.state()))

    def changeRestore_(self, sender):
        self._emit("restore_clipboard", bool(sender.state()))

    def changeProvider_(self, sender):
        self._emit("ai_provider", "local" if sender.selectedSegment() == 0 else "claude")
        self._build()  # Abschnitt passend zum Anbieter neu aufbauen

    def changeClaudeModel_(self, sender):
        self._emit("claude_model", sender.selectedItem().representedObject())

    def changeApiKey_(self, sender):
        key = str(sender.stringValue()).strip()
        if key:
            self._emit("api_key", key)
            sender.setStringValue_("")
            sender.setPlaceholderString_("Gespeichert im Schlüsselbund")

    def changeLogin_(self, sender):
        self._emit("login", bool(sender.state()))

    def openPermission_(self, sender):
        fn = self._perm_actions.get(sender.tag())
        if fn is not None:
            fn()
