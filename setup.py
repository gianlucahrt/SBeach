"""Baut SBeach.app mit py2app.  Aufruf über ./install.sh"""
from setuptools import setup

from sbeach import __version__

PLIST = {
    "CFBundleName": "SBeach",
    "CFBundleDisplayName": "SBeach",
    "CFBundleIdentifier": "app.sbeach.dictation",
    "CFBundleShortVersionString": __version__,
    "CFBundleVersion": __version__,
    "LSUIElement": True,
    "LSMinimumSystemVersion": "13.0",
    "NSHighResolutionCapable": True,
    "NSMicrophoneUsageDescription": (
        "SBeach hört nur während eines Diktats zu. Die Spracherkennung läuft vollständig lokal auf diesem Mac."
    ),
    "NSHumanReadableCopyright": "SBeach. Speech + Beach.",
    "CFBundleDocumentTypes": [{
        "CFBundleTypeName": "Audio und Video",
        "CFBundleTypeRole": "Viewer",
        "LSHandlerRank": "Alternate",
        "LSItemContentTypes": ["public.audio", "public.movie", "public.audiovisual-content",
                               "org.xiph.ogg-audio", "org.xiph.opus"],
    }],
}

setup(
    app=["SBeach.py"],
    name="SBeach",
    version=__version__,
    options={"py2app": {"iconfile": "assets/SBeach.icns", "packages": ["sbeach"], "plist": PLIST}},
    setup_requires=["py2app"],
)
