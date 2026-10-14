"""Nutzungshinweise und Lizenzinformationen, angezeigt in der App."""

from __future__ import annotations

NOTICE_VERSION = 1
REPO_URL = "https://github.com/gianlucahrt/SBeach"

NOTICE_TITLE = "Verantwortungsvoll nutzen"

NOTICE_TEXT = (
    "SBeach ist ein Werkzeug für deine eigene Stimme und deine eigenen Inhalte. "
    "Bitte beachte dabei:\n\n"
    "• Gespräche anderer Personen nur mit deren Einverständnis aufnehmen. "
    "Heimliche Aufnahmen nicht öffentlich gesprochener Worte sind in Deutschland strafbar (§ 201 StGB).\n\n"
    "• Fremde Videos, Audios und Sprachnachrichten nur für dich selbst transkribieren. "
    "Transkripte oder Untertitel fremder Inhalte nicht ohne Erlaubnis veröffentlichen.\n\n"
    "• SBeach nicht für Straftaten, Belästigung, Täuschung oder die Verletzung von Rechten Dritter verwenden.\n\n"
    "• KI Ergebnisse können Fehler enthalten. Prüfe wichtige Texte, bevor du sie versendest.\n\n"
    "Du bist für die Nutzung selbst verantwortlich. SBeach wird ohne jede Gewährleistung "
    "bereitgestellt (MIT Lizenz)."
)

LICENSE_TEXT = (
    "SBeach steht unter der MIT Lizenz.\n\n"
    "Verwendete Bausteine (Auswahl): Whisper (MIT), mlx-whisper (MIT), mlx-lm (MIT), "
    "faster-whisper (MIT), Qwen 2.5 7B Instruct (Apache 2.0), PyObjC (MIT), NumPy (BSD), "
    "sounddevice (MIT), imageio-ffmpeg (BSD 2), FFmpeg (LGPL / GPL), Anthropic SDK (MIT), "
    "keyring (MIT), py2app (MIT).\n\n"
    "Die vollständige Liste steht in THIRD_PARTY_NOTICES.md im Projekt."
)


def notice_accepted(defaults) -> bool:
    return defaults.integerForKey_("SBeachNoticeVersion") >= NOTICE_VERSION


def mark_accepted(defaults) -> None:
    defaults.setInteger_forKey_(NOTICE_VERSION, "SBeachNoticeVersion")


def show_notice(first_run: bool = False) -> None:
    """Zeigt den Nutzungshinweis als natives macOS Dialogfenster."""
    from AppKit import NSAlert, NSApp, NSImage
    from Foundation import NSUserDefaults

    from .ui import theme

    alert = NSAlert.alloc().init()
    alert.setMessageText_(NOTICE_TITLE)
    alert.setInformativeText_(NOTICE_TEXT)
    icon = NSImage.alloc().initWithContentsOfFile_(str(theme.RES / "icon_256.png"))
    if icon is not None:
        alert.setIcon_(icon)
    alert.addButtonWithTitle_("Verstanden")
    if not first_run:
        alert.addButtonWithTitle_("Lizenzen")
    NSApp.activateIgnoringOtherApps_(True)
    response = alert.runModal()
    mark_accepted(NSUserDefaults.standardUserDefaults())
    if response == 1001:  # zweiter Knopf
        show_licenses()


def show_licenses() -> None:
    from AppKit import NSAlert, NSApp, NSURL, NSWorkspace

    alert = NSAlert.alloc().init()
    alert.setMessageText_("Lizenzen")
    alert.setInformativeText_(LICENSE_TEXT)
    alert.addButtonWithTitle_("OK")
    alert.addButtonWithTitle_("Auf GitHub ansehen")
    NSApp.activateIgnoringOtherApps_(True)
    if alert.runModal() == 1001:
        NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(REPO_URL + "/blob/main/THIRD_PARTY_NOTICES.md"))
