"""Audio und Video Dateien lesen, in Abschnitte teilen und als Text exportieren."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import numpy as np

from .textproc import frame_rms

SAMPLE_RATE = 16000
CHUNK_SECONDS = 60.0
SEARCH_SECONDS = 4.0

AUDIO = {"mp3", "m4a", "aac", "wav", "aiff", "aif", "flac", "ogg", "opus", "oga", "caf", "amr", "wma", "webm"}
VIDEO = {"mp4", "mov", "m4v", "mkv", "avi", "3gp", "webm"}
EXTENSIONS = sorted(AUDIO | VIDEO)


def supported(path: str | Path) -> bool:
    return Path(path).suffix.lower().lstrip(".") in EXTENSIONS


def ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def load_audio(path: str | Path) -> np.ndarray:
    """Dekodiert jede gängige Audio oder Videodatei zu 16 kHz Mono float32."""
    cmd = [ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error", "-i", str(path),
           "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        msg = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise RuntimeError(msg[-1] if msg else "Datei konnte nicht gelesen werden")
    audio = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if audio.size == 0:
        raise RuntimeError("Die Datei enthält keine Tonspur")
    return audio


def split_points(audio: np.ndarray, sr: int = SAMPLE_RATE, target: float = CHUNK_SECONDS,
                 search: float = SEARCH_SECONDS) -> list[tuple[int, int]]:
    """Teilt lange Aufnahmen in etwa gleich lange Abschnitte, geschnitten in der leisesten Stelle."""
    n = audio.size
    step = int(target * sr)
    if n <= step * 1.25:
        return [(0, n)]
    frame = 480
    rms = frame_rms(audio, frame)
    bounds = [0]
    pos = step
    while pos < n - step * 0.25:
        lo = max(bounds[-1] + sr, pos - int(search * sr))
        hi = min(n - sr, pos + int(search * sr))
        a, b = lo // frame, max(lo // frame + 1, hi // frame)
        quietest = a + int(np.argmin(rms[a:b])) if b <= rms.size else pos // frame
        cut = quietest * frame + frame // 2
        bounds.append(cut)
        pos = cut + step
    bounds.append(n)
    return list(zip(bounds[:-1], bounds[1:]))


def transcribe_audio(audio: np.ndarray, transcriber, progress: Callable[[float], None] | None = None,
                     cancelled: Callable[[], bool] | None = None):
    """Transkribiert Abschnitt für Abschnitt; die Sprache des ersten Abschnitts gilt für alle."""
    chunks = split_points(audio)
    segments: list[tuple[float, float, str]] = []
    language = None
    for i, (a, b) in enumerate(chunks):
        if cancelled is not None and cancelled():
            raise InterruptedError
        segs, detected = transcriber.transcribe_segments(audio[a:b], language=language)
        language = language or detected
        offset = a / SAMPLE_RATE
        segments.extend((s + offset, e + offset, t) for s, e, t in segs)
        if progress is not None:
            progress((i + 1) / len(chunks))
    return segments, language or ""


def plain_text(segments) -> str:
    """Segmente zu Fließtext, mit Absatz bei längeren Pausen."""
    out = []
    last_end = None
    for start, end, text in segments:
        if last_end is not None:
            out.append("\n\n" if start - last_end > 2.0 else " ")
        out.append(text.strip())
        last_end = end
    return "".join(out).strip()


def _ts(seconds: float) -> str:
    ms = int(round(max(0.0, seconds) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(segments) -> str:
    blocks = []
    for i, (start, end, text) in enumerate(segments, 1):
        end = max(end, start + 0.5)
        blocks.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text.strip()}\n")
    return "\n".join(blocks)


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
