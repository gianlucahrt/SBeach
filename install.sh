#!/bin/bash
# Installiert SBeach als App in /Applications.
set -euo pipefail
cd "$(dirname "$0")"

if [[ "$(uname)" != "Darwin" ]]; then echo "SBeach läuft nur auf macOS."; exit 1; fi

PY="${PYTHON:-}"
for candidate in python3.12 python3.11 python3.13 python3.10 python3; do
  if [[ -z "$PY" ]] && command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then PY="$candidate"; fi
  fi
done
if [[ -z "$PY" ]]; then echo "Bitte Python 3.10 oder neuer installieren (z.B. brew install python@3.12)."; exit 1; fi

echo "▸ Python: $($PY --version)"
"$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel >/dev/null
echo "▸ Abhängigkeiten werden installiert (einmalig, dauert etwas)…"
python -m pip install -r requirements.txt py2app

echo "▸ SBeach.app wird gebaut…"
rm -rf build dist
python setup.py py2app -A >/dev/null
codesign --force --deep -s - dist/SBeach.app >/dev/null 2>&1 || true


rm -rf /Applications/SBeach.app
cp -R dist/SBeach.app /Applications/
echo "✓ Installiert: /Applications/SBeach.app"
echo "  Beim ersten Start fragt macOS nach Mikrofon, Bedienungshilfen und Eingabeüberwachung."
open /Applications/SBeach.app
