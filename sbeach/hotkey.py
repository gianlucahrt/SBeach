"""Globaler Hotkey über einen Quartz Event Tap.

Die Entscheidungslogik (HotkeyLogic) ist reines Python und testbar. Nur HotkeyTap
benötigt macOS. Ein eigener Event Tap statt pynput, weil er ausschließlich Keycodes
auswertet (keine Zeichenübersetzung abseits des Main Threads) und damit auf aktuellen
macOS Versionen stabil läuft.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# Gerätespezifische Flag Bits (IOLLEvent.h), damit links und rechts unterscheidbar sind.
NX_DEVICERCTLKEYMASK = 0x00002000
NX_DEVICERSHIFTKEYMASK = 0x00000004
NX_DEVICERCMDKEYMASK = 0x00000010
NX_DEVICERALTKEYMASK = 0x00000040
FLAG_SECONDARY_FN = 0x00800000

KEY_ESCAPE = 53

# name: (Anzeigename im Menü, Kurzform, keycode, Flag Maske oder None für normale Tasten)
HOTKEYS: dict[str, tuple[str, str, int, int | None]] = {
    "alt_r": ("Option rechts", "⌥ rechts", 61, NX_DEVICERALTKEYMASK),
    "cmd_r": ("Command rechts", "⌘ rechts", 54, NX_DEVICERCMDKEYMASK),
    "ctrl_r": ("Control rechts", "⌃ rechts", 62, NX_DEVICERCTLKEYMASK),
    "shift_r": ("Shift rechts", "⇧ rechts", 60, NX_DEVICERSHIFTKEYMASK),
    "fn": ("Fn / Globus", "fn", 63, FLAG_SECONDARY_FN),
    "f13": ("F13", "F13", 105, None),
    "f14": ("F14", "F14", 107, None),
    "f15": ("F15", "F15", 113, None),
    "f16": ("F16", "F16", 106, None),
    "f17": ("F17", "F17", 64, None),
    "f18": ("F18", "F18", 79, None),
    "f19": ("F19", "F19", 80, None),
}


class HotkeyLogic:
    """Übersetzt rohe Tastaturereignisse in Hotkey Ereignisse.

    Ausgaben:
      "down"      Hotkey wurde gedrückt
      "up"        Hotkey losgelassen, ohne dass dazwischen eine andere Taste kam
      "up_chord"  Hotkey losgelassen, war aber Teil einer Tastenkombination (z.B. ⌥ + L für @)
      "chord"     Während der Hotkey gehalten wird, kam eine andere Taste dazu
      "escape"    Esc wurde gedrückt
    """

    def __init__(self, name: str = "alt_r"):
        self.set_key(name)

    def set_key(self, name: str) -> None:
        if name not in HOTKEYS:
            name = "alt_r"
        self.name = name
        _, _, self.code, self.mask = HOTKEYS[name]
        self.down = False
        self.chord = False

    def _press(self) -> list[str]:
        self.down = True
        self.chord = False
        return ["down"]

    def _release(self) -> list[str]:
        self.down = False
        return ["up_chord" if self.chord else "up"]

    def _mark_chord(self) -> list[str]:
        if self.down and not self.chord:
            self.chord = True
            return ["chord"]
        return []

    def feed(self, kind: str, keycode: int, flags: int = 0, autorepeat: bool = False) -> list[str]:
        """kind: "flags" (Modifier geändert), "keydown" oder "keyup"."""
        if kind == "flags":
            if self.mask is not None and keycode == self.code:
                pressed = bool(flags & self.mask)
                if pressed and not self.down:
                    return self._press()
                if not pressed and self.down:
                    return self._release()
                return []
            # Ein anderer Modifier ändert sich, während der Hotkey gehalten wird
            return self._mark_chord()

        if kind == "keydown":
            if self.mask is None and keycode == self.code:
                if autorepeat or self.down:
                    return []
                return self._press()
            if keycode == KEY_ESCAPE:
                return ["escape"]
            return self._mark_chord()

        if kind == "keyup":
            if self.mask is None and keycode == self.code and self.down:
                return self._release()
        return []


class HotkeyTap:
    """Hängt einen passiven (listen only) Event Tap an den Main Run Loop."""

    def __init__(self, name: str, callback):
        self.logic = HotkeyLogic(name)
        self.callback = callback
        self._tap = None
        self._source = None
        self._handler = None

    def set_key(self, name: str) -> None:
        self.logic.set_key(name)

    def start(self) -> bool:
        import Quartz as Q

        mask = (
            Q.CGEventMaskBit(Q.kCGEventKeyDown)
            | Q.CGEventMaskBit(Q.kCGEventKeyUp)
            | Q.CGEventMaskBit(Q.kCGEventFlagsChanged)
        )

        def handler(proxy, event_type, event, refcon):
            try:
                if event_type in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
                    if self._tap is not None:
                        Q.CGEventTapEnable(self._tap, True)
                    return event
                keycode = Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode)
                flags = Q.CGEventGetFlags(event)
                if event_type == Q.kCGEventFlagsChanged:
                    kind = "flags"
                elif event_type == Q.kCGEventKeyDown:
                    kind = "keydown"
                else:
                    kind = "keyup"
                repeat = bool(Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventAutorepeat))
                for ev in self.logic.feed(kind, int(keycode), int(flags), repeat):
                    self.callback(ev)
            except Exception:  # Ein Fehler darf den Tap nie beenden
                log.exception("Fehler im Hotkey Handler")
            return event

        self._handler = handler  # Referenz halten, sonst räumt der GC den Callback weg
        self._tap = Q.CGEventTapCreate(
            Q.kCGSessionEventTap,
            Q.kCGHeadInsertEventTap,
            Q.kCGEventTapOptionListenOnly,
            mask,
            handler,
            None,
        )
        if self._tap is None:
            log.warning("Event Tap konnte nicht erstellt werden (Eingabeüberwachung fehlt?)")
            return False
        self._source = Q.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Q.CFRunLoopAddSource(Q.CFRunLoopGetMain(), self._source, Q.kCFRunLoopCommonModes)
        Q.CGEventTapEnable(self._tap, True)
        log.info("Hotkey aktiv: %s", self.logic.name)
        return True

    def stop(self) -> None:
        if self._tap is None:
            return
        import Quartz as Q

        Q.CGEventTapEnable(self._tap, False)
        if self._source is not None:
            Q.CFRunLoopRemoveSource(Q.CFRunLoopGetMain(), self._source, Q.kCFRunLoopCommonModes)
        self._tap = None
        self._source = None
