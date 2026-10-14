#!/bin/bash
# Prüft die lokale Spracherkennung mit Sprachausgabe von macOS.
cd "$(dirname "$0")"
source .venv/bin/activate
T=$(mktemp -d)
say -v Anna -o "$T/de.aiff" "Hallo, das ist ein Test von SBeach. Die Spracherkennung läuft komplett lokal auf meinem Mac."
say -v Samantha -o "$T/en.aiff" "Please schedule the meeting for Thursday at three thirty."
python - "$T" > asr_test.log 2>&1 <<'PY'
import sys, time, subprocess, numpy as np
from sbeach.transcriber import Transcriber
from sbeach import textproc
T = sys.argv[1]
def load(name):
    raw = subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", "-c", "1", f"{T}/{name}.aiff", f"{T}/{name}.wav"], check=True)
    import wave
    w = wave.open(f"{T}/{name}.wav"); data = np.frombuffer(w.readframes(w.getnframes()), np.int16)
    return data.astype(np.float32) / 32768
tr = Transcriber(model="balanced", language="auto")
t = time.time(); tr.load(); print(f"Modell geladen: {time.time()-t:.1f}s")
for name in ("de", "en"):
    audio = load(name)
    t = time.time(); text, lang = tr.transcribe(audio)
    print(f"[{lang}] {len(audio)/16000:.1f}s Audio in {time.time()-t:.2f}s: {textproc.clean(text, trailing_space=False)}")
PY
echo "EXIT=$?" >> asr_test.log
