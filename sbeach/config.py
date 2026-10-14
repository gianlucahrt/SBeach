"""Einstellungen von SBeach, gespeichert als JSON im Application Support Ordner."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import APP_NAME

DEFAULTS: dict = {
    # "hold": Taste halten, sprechen, loslassen. "toggle": einmal drücken startet, nochmal stoppt.
    "mode": "hold",
    # Siehe hotkey.HOTKEYS
    "hotkey": "alt_r",
    # "fast" | "balanced" | "precise" (siehe transcriber.MODELS)
    "model": "balanced",
    # "auto" | "mlx" | "faster-whisper"
    "backend": "auto",
    # "auto" erkennt die Sprache, beschränkt auf allowed_languages
    "language": "auto",
    "allowed_languages": ["de", "en"],
    "fallback_language": "de",
    # "paste" (über Zwischenablage, schnell und zuverlässig) | "type" (simuliertes Tippen)
    "insert_method": "paste",
    "restore_clipboard": True,
    "trailing_space": True,
    "sounds": True,
    # Eigene Begriffe, Namen, Fachwörter. Werden Whisper als Kontext mitgegeben.
    "vocabulary": ["SBeach"],
    "history_size": 20,
    # None = Standardmikrofon
    "input_device": None,
    # KI: "local" (MLX auf dem Mac) | "claude" (Anthropic API, nur Text)
    "ai_provider": "local",
    "claude_model": "claude-sonnet-5-5",
    "local_model": "mlx-community/Qwen2.5-7B-Instruct-4bit",
}


def support_dir() -> Path:
    base = os.environ.get("SBEACH_HOME")
    if base:
        path = Path(base)
    else:
        path = Path.home() / "Library" / "Application Support" / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return support_dir() / "config.json"


def log_path() -> Path:
    logs = Path.home() / "Library" / "Logs"
    if not logs.exists() or os.environ.get("SBEACH_HOME"):
        return support_dir() / "sbeach.log"
    return logs / "SBeach.log"


class Config:
    """Dünne Hülle um ein dict mit Standardwerten, Validierung und Speichern."""

    VALID = {
        "mode": {"hold", "toggle"},
        "model": {"fast", "balanced", "precise"},
        "backend": {"auto", "mlx", "faster-whisper"},
        "insert_method": {"paste", "type"},
        "ai_provider": {"local", "claude"},
    }

    def __init__(self, path: Path | None = None):
        self.path = path or config_path()
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        loaded = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    loaded = {}
            except (OSError, ValueError):
                loaded = {}
        data = dict(DEFAULTS)
        for key, value in loaded.items():
            if key in DEFAULTS:
                data[key] = value
        for key, allowed in self.VALID.items():
            if data[key] not in allowed:
                data[key] = DEFAULTS[key]
        if not isinstance(data["vocabulary"], list):
            data["vocabulary"] = []
        self.data = data
        if not self.path.exists():
            self.save()

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def __getitem__(self, key):
        return self.data[key]

    def set(self, key, value) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        if key in self.VALID and value not in self.VALID[key]:
            raise ValueError(f"Ungültiger Wert für {key}: {value!r}")
        self.data[key] = value
        self.save()
