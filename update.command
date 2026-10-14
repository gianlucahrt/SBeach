#!/bin/bash
# Aktualisiert SBeach: Abhängigkeiten, App neu bauen, Oberfläche rendern, neu starten.
cd "$(dirname "$0")"
exec > update.log 2>&1
pkill -x SBeach; pkill -f "python -m sbeach$"
source .venv/bin/activate
python -m pip install -q -r requirements.txt && echo "PIP=ok"
rm -rf build dist
python setup.py py2app -A >/dev/null && echo "BUILD=ok"
codesign --force --deep -s - dist/SBeach.app >/dev/null 2>&1
rm -rf /Applications/SBeach.app && cp -R dist/SBeach.app /Applications/
mkdir -p snapshots && python -m sbeach --snapshot snapshots && echo "SNAP=ok"
open /Applications/SBeach.app
echo "EXIT=done"
