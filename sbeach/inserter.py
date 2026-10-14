"""Text direkt in die aktive Anwendung einfügen.

Standard: Text kurz in die Zwischenablage legen, ⌘V senden, danach die vorherige
Zwischenablage wiederherstellen. Das ist schnell, unterstützt Umlaute und Emoji und
funktioniert in praktisch jeder App. Alternativ wird das Tippen simuliert, für Felder,
die kein Einfügen erlauben.
"""

from __future__ import annotations

import logging
import time

log = logging.getLogger(__name__)

KEY_V = 9  # Position von V ist auf QWERTZ und QWERTY identisch
TRANSIENT_TYPE = "org.nspasteboard.TransientType"  # Clipboard Manager ignorieren den Eintrag
CONCEALED_TYPE = "org.nspasteboard.ConcealedType"


def accessibility_trusted(prompt: bool = False) -> bool:
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))
    except Exception:
        log.exception("Bedienungshilfen Status nicht abfragbar")
        return False


def secure_input_active() -> bool:
    """True, wenn gerade ein Passwortfeld o.ä. aktiv ist (dann blockt macOS Eingaben)."""
    try:
        import ctypes

        carbon = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Carbon.framework/Carbon")
        carbon.IsSecureEventInputEnabled.restype = ctypes.c_bool
        return bool(carbon.IsSecureEventInputEnabled())
    except Exception:
        return False


def _snapshot(pb):
    items = []
    for item in pb.pasteboardItems() or []:
        entry = {}
        for t in item.types() or []:
            data = item.dataForType_(t)
            if data is not None:
                entry[t] = data
        if entry:
            items.append(entry)
    return items


def _restore(pb, items, change_count):
    from AppKit import NSPasteboardItem

    # Hat der Nutzer in der Zwischenzeit selbst etwas kopiert, nichts überschreiben.
    if pb.changeCount() != change_count:
        return
    pb.clearContents()
    if not items:
        return
    restored = []
    for entry in items:
        item = NSPasteboardItem.alloc().init()
        for t, data in entry.items():
            item.setData_forType_(data, t)
        restored.append(item)
    pb.writeObjects_(restored)


def _post_cmd_v():
    import Quartz as Q

    src = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
    down = Q.CGEventCreateKeyboardEvent(src, KEY_V, True)
    up = Q.CGEventCreateKeyboardEvent(src, KEY_V, False)
    Q.CGEventSetFlags(down, Q.kCGEventFlagMaskCommand)
    Q.CGEventSetFlags(up, Q.kCGEventFlagMaskCommand)
    Q.CGEventPost(Q.kCGHIDEventTap, down)
    Q.CGEventPost(Q.kCGHIDEventTap, up)


def paste_text(text: str, restore: bool = True, schedule=None) -> None:
    """Muss auf dem Main Thread laufen. schedule(delay, fn) plant die Wiederherstellung."""
    from AppKit import NSPasteboard, NSPasteboardTypeString

    pb = NSPasteboard.generalPasteboard()
    saved = _snapshot(pb) if restore else None
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)
    pb.setString_forType_("", TRANSIENT_TYPE)
    pb.setString_forType_("", CONCEALED_TYPE)
    ours = pb.changeCount()
    _post_cmd_v()
    if restore:
        def do_restore():
            try:
                _restore(pb, saved, ours)
            except Exception:
                log.exception("Zwischenablage konnte nicht wiederhergestellt werden")

        if schedule is not None:
            schedule(0.45, do_restore)
        else:
            time.sleep(0.45)
            do_restore()


def type_text(text: str, chunk: int = 16, delay: float = 0.004) -> None:
    import Quartz as Q

    src = Q.CGEventSourceCreate(Q.kCGEventSourceStateHIDSystemState)
    for i in range(0, len(text), chunk):
        part = text[i:i + chunk]
        down = Q.CGEventCreateKeyboardEvent(src, 0, True)
        up = Q.CGEventCreateKeyboardEvent(src, 0, False)
        Q.CGEventSetFlags(down, 0)
        Q.CGEventSetFlags(up, 0)
        Q.CGEventKeyboardSetUnicodeString(down, len(part), part)
        Q.CGEventKeyboardSetUnicodeString(up, len(part), part)
        Q.CGEventPost(Q.kCGHIDEventTap, down)
        Q.CGEventPost(Q.kCGHIDEventTap, up)
        time.sleep(delay)


def insert(text: str, method: str = "paste", restore: bool = True, schedule=None) -> None:
    if not text:
        return
    if method == "type":
        type_text(text)
    else:
        paste_text(text, restore=restore, schedule=schedule)
