"""Equalizer Pegel aus einem Audioblock berechnen (reines numpy, plattformunabhängig)."""

from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16000


def compute_bands(block: np.ndarray, n: int, sr: int = SAMPLE_RATE,
                  lo: float = 90.0, hi: float = 6500.0) -> np.ndarray:
    """Liefert n Werte zwischen 0 und 1, logarithmisch über das Sprachband verteilt."""
    if n <= 0:
        return np.zeros(0)
    if block is None or block.size < 64:
        return np.zeros(n)
    block = block.astype(np.float64)
    window = np.hanning(block.size)
    spec = np.abs(np.fft.rfft(block * window))
    freqs = np.fft.rfftfreq(block.size, 1.0 / sr)
    edges = np.geomspace(lo, hi, n + 1)
    values = np.empty(n)
    for i in range(n):
        mask = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if mask.any():
            values[i] = spec[mask].max()
        else:
            center = np.sqrt(edges[i] * edges[i + 1])
            values[i] = spec[int(np.argmin(np.abs(freqs - center)))]
    # Ein Vollaussteuerungs Sinus hat mit Hann Fenster etwa die Amplitude N/4.
    ref = block.size / 4.0
    db = 20.0 * np.log10(values / ref + 1e-12)
    # Sprache landet typischerweise zwischen -60 und -10 dBFS
    return np.clip((db + 62.0) / 50.0, 0.0, 1.0)
