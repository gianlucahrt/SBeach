"""Symbol und kompaktes Menü in der macOS Menüleiste."""

from __future__ import annotations

import objc
from AppKit import NSMenu, NSMenuItem, NSStatusBar, NSVariableStatusItemLength
from Foundation import NSObject

from . import theme


class StatusMenu(NSObject):
    def init(self):
        self = objc.super(StatusMenu, self).init()
        if self is None:
            return None
        self.actions = {}   # name -> callable
        self.state = lambda: {}
        self.history = lambda: []
        self.icon_idle = theme.resource_image("menubarTemplate@2x.png", 18, template=True)
        self.icon_rec = theme.resource_image("menubar_rec@2x.png", 18, template=False)
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        button = self.item.button()
        button.setImage_(self.icon_idle)
        button.setToolTip_("SBeach")
        button.setAccessibilityLabel_("SBeach")
        self.menu = NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(False)
        self.menu.setDelegate_(self)
        self.item.setMenu_(self.menu)
        self.recording = False
        return self

    @objc.python_method
    def set_recording(self, recording: bool) -> None:
        if recording != self.recording:
            self.recording = recording
            self.item.button().setImage_(self.icon_rec if recording else self.icon_idle)

    # Menü ---------------------------------------------------------------
    def menuNeedsUpdate_(self, menu):
        menu.removeAllItems()
        s = self.state()
        self._add(menu, f"SBeach   {s.get('status_text', '')}", None)
        record_title = "Aufnahme beenden" if s.get("recording") else "Diktat starten"
        self._add(menu, record_title, "doRecord:")
        if s.get("hint"):
            self._add(menu, s["hint"], None)
        menu.addItem_(NSMenuItem.separatorItem())
        window_title = "Fenster ausblenden" if s.get("window_visible") else "SBeach Fenster zeigen"
        self._add(menu, window_title, "doWindow:")
        self._add(menu, "Datei transkribieren …", "doFile:", "o")

        history = list(self.history())
        sub = NSMenu.alloc().init()
        sub.setAutoenablesItems_(False)
        if history:
            for text in history[:10]:
                short = text if len(text) <= 48 else text[:47].rstrip() + "…"
                item = self._add(sub, short, "doCopy:")
                item.setRepresentedObject_(text)
                item.setToolTip_("Klicken zum Kopieren")
        else:
            self._add(sub, "Noch keine Diktate", None)
        parent = self._add(menu, "Zuletzt diktiert", None)
        parent.setEnabled_(True)
        parent.setSubmenu_(sub)

        menu.addItem_(NSMenuItem.separatorItem())
        self._add(menu, "Einstellungen …", "doSettings:", ",")
        self._add(menu, "SBeach beenden", "doQuit:", "q")

    @objc.python_method
    def _add(self, menu, title, action, key=""):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        if action:
            item.setTarget_(self)
        else:
            item.setEnabled_(False)
        menu.addItem_(item)
        return item

    @objc.python_method
    def _run(self, name, *args):
        fn = self.actions.get(name)
        if fn is not None:
            fn(*args)

    def doRecord_(self, sender):
        self._run("record")

    def doWindow_(self, sender):
        self._run("window")

    def doCopy_(self, sender):
        self._run("copy", sender.representedObject())

    def doFile_(self, sender):
        self._run("file")

    def doSettings_(self, sender):
        self._run("settings")

    def doQuit_(self, sender):
        self._run("quit")
