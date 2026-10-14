"""Mikrofonaufnahme mit 16 kHz Mono, plus Live Pegel für den Equalizer."""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

from .levels import compute_bands

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BLOCK = 512  # 32 ms, gute Balance aus Latenz und Equalizer Auflösung
MAX_SECONDS = 15 * 60


class Recorder:
    """Öffnet den Mikrofonstream nur während der Aufnahme.

    So ist der orangefarbene Mikrofonpunkt von macOS nur sichtbar, wenn wirklich
    diktiert wird.
    """

    def __init__(self, device=None):
        self.device = device
        self._lock = threading.Lock()
        self._chunks: list[np.ndarray] = []
        self._last = np.zeros(BLOCK, dtype=np.float32)
        self._stream = None
        self._samples = 0
        self.started_at: float | None = None

    @property
    def active(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        if self._stream is not None:
            return
        with self._lock:
            self._chunks = []
            self._samples = 0
            self._last = np.zeros(BLOCK, dtype=np.float32)
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK,
            device=self.device,
            latency="low",
            callback=self._callback,
        )
        self._stream.start()
        self.started_at = time.monotonic()

    def _callback(self, indata, frames, time_info, status):  # läuft im Audio Thread
        if status:
            log.debug("Audio Status: %s", status)
        mono = indata[:, 0].copy()
        with self._lock:
            if self._samples < MAX_SECONDS * SAMPLE_RATE:
                self._chunks.append(mono)
                self._samples += mono.size
            self._last = mono

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                log.exception("Stream konnte nicht sauber geschlossen werden")

    def stop(self) -> np.ndarray:
        self._close()
        with self._lock:
            chunks, self._chunks = self._chunks, []
        self.started_at = None
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def cancel(self) -> None:
        self._close()
        with self._lock:
            self._chunks = []
        self.started_at = None

    def elapsed(self) -> float:
        return 0.0 if self.started_at is None else time.monotonic() - self.started_at

    def band_levels(self, n: int) -> np.ndarray:
        with self._lock:
            block = self._last.copy()
        return compute_bands(block, n)


def input_devices() -> list[tuple[int, str]]:
    import sounddevice as sd

    result = []
    for idx, dev in enumerate(sd.query_devices()):
        if dev.get("max_input_channels", 0) > 0:
            result.append((idx, dev["name"]))
    return result
