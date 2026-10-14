#!/bin/bash
# Prüft Datei Transkription (m4a und mp4) und das lokale Sprachmodell.
cd "$(dirname "$0")"
source .venv/bin/activate
T=$(mktemp -d)
say -v Anna --file-format=m4af -o "$T/sprachnachricht.m4a" "Hey, ich wollte kurz Bescheid sagen. Das Treffen am Donnerstag verschiebt sich auf Freitag um 15 Uhr, weil Lisa noch im Urlaub ist. Kannst du bitte den Raum neu buchen und den anderen Bescheid geben? Danke dir!"
FF=$(python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
"$FF" -loglevel error -f lavfi -i color=c=black:s=320x240:d=12 -i "$T/sprachnachricht.m4a" -shortest -c:v libx264 -c:a aac "$T/video.mp4"
python - "$T" > ai_test.log 2>&1 <<'PY'
import sys, time
from sbeach import media, llm
from sbeach.config import Config
from sbeach.transcriber import Transcriber
T = sys.argv[1]
tr = Transcriber(model="balanced")
for name in ("sprachnachricht.m4a", "video.mp4"):
    t = time.time(); audio = media.load_audio(f"{T}/{name}")
    segs, lang = media.transcribe_audio(audio, tr)
    print(f"[{name}] {len(audio)/16000:.1f}s, {lang}, {time.time()-t:.1f}s:\n{media.plain_text(segs)}\n")
print(media.to_srt(segs)[:200])
text = media.plain_text(segs)
a = llm.Assistant(Config())
for preset in (llm.PRESETS[0], llm.PRESETS[2]):
    t = time.time(); out = a.run(preset.instruction, text)
    print(f"--- {preset.label} ({time.time()-t:.1f}s) ---\n{out}\n", flush=True)
PY
echo "EXIT=$?" >> ai_test.log
