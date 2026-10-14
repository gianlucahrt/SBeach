"""Lokale Spracherkennung mit Whisper.

Auf Apple Silicon wird mlx-whisper genutzt (läuft auf der GPU, sehr schnell).
Auf Intel Macs oder als Fallback faster-whisper (CPU, int8).
Es werden keinerlei Audiodaten ins Netz geschickt. Nur beim allerersten Start
wird das Modell einmalig von Hugging Face geladen und danach lokal gecacht.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import platform
import threading
import time

import numpy as np

from .textproc import build_prompt

log = logging.getLogger(__name__)

MODELS = {
    "fast": {
        "label": "Schnell",
        "hint": "small, ideal für ältere Macs",
        "mlx": "mlx-community/whisper-small-mlx",
        "fw": "small",
    },
    "balanced": {
        "label": "Ausgewogen",
        "hint": "large v3 turbo, empfohlen",
        "mlx": "mlx-community/whisper-large-v3-turbo",
        "fw": "large-v3-turbo",
    },
    "precise": {
        "label": "Präzise",
        "hint": "large v3, langsamer",
        "mlx": "mlx-community/whisper-large-v3-mlx",
        "fw": "large-v3",
    },
}

LANGUAGE_LABELS = {"auto": "Automatisch (DE / EN)", "de": "Deutsch", "en": "Englisch"}


def apple_silicon() -> bool:
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def _has(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def pick_backend(preference: str = "auto") -> str:
    if preference in ("auto", "mlx") and apple_silicon() and _has("mlx_whisper"):
        return "mlx"
    if _has("faster_whisper"):
        return "faster-whisper"
    if preference == "mlx" and _has("mlx_whisper"):
        return "mlx"
    raise RuntimeError(
        "Keine Spracherkennung installiert. Bitte ./install.sh ausführen "
        "(installiert mlx-whisper bzw. faster-whisper)."
    )


class Transcriber:
    def __init__(self, model: str = "balanced", language: str = "auto",
                 allowed=("de", "en"), fallback: str = "de",
                 backend: str = "auto", vocabulary=None):
        self.model_key = model if model in MODELS else "balanced"
        self.language = language
        self.allowed = tuple(allowed) or ("de", "en")
        self.fallback = fallback if fallback in self.allowed else self.allowed[0]
        self.backend_pref = backend
        self.prompt = build_prompt(vocabulary or [])
        self.backend: str | None = None
        self._fw_model = None
        self._mlx_path: str | None = None
        self._loaded_key: str | None = None
        self._lock = threading.Lock()

    # Konfiguration -------------------------------------------------------
    def configure(self, *, model=None, language=None, vocabulary=None, backend=None):
        with self._lock:
            if model is not None and model in MODELS:
                self.model_key = model
            if language is not None:
                self.language = language
            if vocabulary is not None:
                self.prompt = build_prompt(vocabulary)
            if backend is not None:
                self.backend_pref = backend

    @property
    def ready(self) -> bool:
        return self._loaded_key == self._wanted_key()

    def _wanted_key(self) -> str:
        return f"{self.backend_pref}:{self.model_key}"

    def model_name(self) -> str:
        info = MODELS[self.model_key]
        return info["mlx"] if self.backend == "mlx" else info["fw"]

    # Laden ---------------------------------------------------------------
    def load(self) -> None:
        """Lädt das Modell (beim ersten Mal inkl. Download) und wärmt es auf."""
        with self._lock:
            if self.ready:
                return
            started = time.monotonic()
            self.backend = pick_backend(self.backend_pref)
            if self.backend == "faster-whisper":
                from faster_whisper import WhisperModel

                self._fw_model = WhisperModel(
                    MODELS[self.model_key]["fw"],
                    device="cpu",
                    compute_type="int8",
                    cpu_threads=max(1, (os.cpu_count() or 4) - 1),
                )
            else:
                self._fw_model = None
                self._mlx_path = self._local_mlx_model(MODELS[self.model_key]["mlx"])
            # Aufwärmen: erste Inferenz kompiliert Kernel bzw. lädt Gewichte
            self._run(np.zeros(16000, dtype=np.float32), "de")
            self._loaded_key = self._wanted_key()
            log.info("Modell %s (%s) bereit nach %.1fs", self.model_name(), self.backend,
                     time.monotonic() - started)

    @staticmethod
    def _local_mlx_model(repo: str) -> str:
        """Lokalen Pfad liefern; nur wenn das Modell fehlt, einmalig herunterladen."""
        from huggingface_hub import snapshot_download

        try:
            return snapshot_download(repo, local_files_only=True)
        except Exception:
            log.info("Lade Modell %s einmalig herunter", repo)
            return snapshot_download(repo)

    # Erkennen ------------------------------------------------------------
    def transcribe(self, audio: np.ndarray) -> tuple[str, str]:
        """Diktat: gibt (Text, Sprache) zurück, Sprache beschränkt auf DE/EN."""
        self.load()
        with self._lock:
            lang = None if self.language == "auto" else self.language
            text, detected, _ = self._run(audio, lang)
            return text, detected

    def transcribe_segments(self, audio: np.ndarray, language: str | None = None,
                            restrict: bool = False) -> tuple[list[tuple[float, float, str]], str]:
        """Dateien: Segmente mit Zeitstempeln. Ohne restrict sind alle Sprachen erlaubt."""
        self.load()
        with self._lock:
            _, detected, segments = self._run(audio, language, restrict=restrict, timestamps=True)
            return segments, detected

    def _run(self, audio: np.ndarray, language: str | None, restrict: bool = True,
             timestamps: bool = False):
        audio = np.ascontiguousarray(audio, dtype=np.float32)
        if self.backend == "mlx":
            return self._run_mlx(audio, language, restrict)
        return self._run_fw(audio, language, restrict, timestamps)

    def _run_mlx(self, audio, language, restrict=True):
        import mlx_whisper

        repo = self._mlx_path or MODELS[self.model_key]["mlx"]

        def once(lang):
            return mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=repo,
                language=lang,
                initial_prompt=self.prompt,
                condition_on_previous_text=False,
                temperature=(0.0, 0.2, 0.4),
                verbose=None,
            )

        result = once(language)
        detected = result.get("language") or language or self.fallback
        if restrict and language is None and detected not in self.allowed:
            log.info("Erkannte Sprache %s nicht erlaubt, wiederhole mit %s", detected, self.fallback)
            detected = self.fallback
            result = once(detected)
        segments = [(float(s["start"]), float(s["end"]), s["text"].strip())
                    for s in result.get("segments") or [] if s.get("text", "").strip()]
        return (result.get("text") or "").strip(), detected, segments

    def _run_fw(self, audio, language, restrict=True, timestamps=False):
        model = self._fw_model
        kwargs = dict(
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
            initial_prompt=self.prompt,
            without_timestamps=not timestamps,
        )
        segments, info = model.transcribe(audio, language=language, **kwargs)
        detected = info.language or language or self.fallback
        if restrict and language is None and detected not in self.allowed:
            probs = dict(getattr(info, "all_language_probs", None) or [])
            best = max(self.allowed, key=lambda code: probs.get(code, 0.0))
            log.info("Erkannte Sprache %s nicht erlaubt, nutze %s", detected, best)
            detected = best
            segments, info = model.transcribe(audio, language=best, **kwargs)
        segs = [(float(s.start), float(s.end), s.text.strip()) for s in segments if s.text.strip()]
        text = " ".join(t for _, _, t in segs).strip()
        return text, detected, segs
