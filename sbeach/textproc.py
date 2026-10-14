"""Reine Textlogik: Stilleerkennung, Bereinigung und typische Whisper Halluzinationen."""

from __future__ import annotations

import re

import numpy as np

SAMPLE_RATE = 16000

# Diese Sätze erzeugt Whisper bei Stille oder Rauschen, sie sind praktisch nie echtes Diktat.
ALWAYS_DROP = {
    "untertitel der amaraorg community",
    "untertitel im auftrag des zdf für funk 2017",
    "untertitel im auftrag des zdf 2017",
    "untertitel im auftrag des zdf 2018",
    "untertitelung des zdf 2020",
    "untertitel von stephanie geiges",
    "copyright wdr 2021",
    "subtitles by the amaraorg community",
    "thanks for watching",
    "thank you for watching",
    "bis zum nächsten mal",
}

# Diese Sätze können echt sein ("Vielen Dank."), werden aber nur verworfen, wenn kaum Sprache da war.
DROP_IF_QUIET = {
    "vielen dank",
    "danke",
    "danke schön",
    "dankeschön",
    "tschüss",
    "thank you",
    "thanks",
    "you",
    "bye",
    "okay",
}


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


ALWAYS_DROP = {_key(s) for s in ALWAYS_DROP} | {_key("Untertitel der Amara.org-Community")}
DROP_IF_QUIET = {_key(s) for s in DROP_IF_QUIET}


def frame_rms(audio: np.ndarray, frame: int = 480) -> np.ndarray:
    """RMS je 30 ms Fenster (bei 16 kHz)."""
    if audio.size < frame:
        return np.array([float(np.sqrt(np.mean(audio**2)))]) if audio.size else np.zeros(1)
    usable = audio[: audio.size - audio.size % frame].reshape(-1, frame)
    return np.sqrt(np.mean(usable.astype(np.float64) ** 2, axis=1))


def speech_level(audio: np.ndarray) -> float:
    """Pegel der lautesten Passagen (95. Perzentil der Fenster RMS)."""
    return float(np.percentile(frame_rms(audio), 95))


def is_silent(audio: np.ndarray, threshold: float = 0.006) -> bool:
    return audio.size < SAMPLE_RATE * 0.2 or speech_level(audio) < threshold


def is_quiet(audio: np.ndarray, threshold: float = 0.015) -> bool:
    return speech_level(audio) < threshold


def clean(text: str, quiet: bool = False, trailing_space: bool = True) -> str:
    """Whitespace normalisieren und Halluzinationen verwerfen."""
    text = " ".join((text or "").split()).strip()
    if not text:
        return ""
    key = _key(text)
    if not key or key in ALWAYS_DROP:
        return ""
    if quiet and key in DROP_IF_QUIET:
        return ""
    # Wiederholungsschleifen ("das das das das ...") auf ein Vorkommen kürzen
    text = re.sub(r"\b(\w+)(?:[ ,]+\1\b){3,}", r"\1", text, flags=re.IGNORECASE)
    if trailing_space:
        text += " "
    return text


def build_prompt(vocabulary: list[str]) -> str | None:
    words = [w.strip() for w in vocabulary if isinstance(w, str) and w.strip()]
    if not words:
        return None
    return ", ".join(words[:60]) + "."
