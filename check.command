#!/bin/bash
# Selbstprüfung: beendet laufende SBeach Instanzen, rendert die Oberfläche, startet SBeach neu.
cd "$(dirname "$0")"
pkill -x SBeach; pkill -f "python -m sbeach$"; sleep 1
source .venv/bin/activate
mkdir -p snapshots
python -m sbeach --snapshot snapshots > check.log 2>&1
echo "EXIT=$?" >> check.log
open /Applications/SBeach.app
sleep 2
open /Applications/SBeach.app
sleep 3
pgrep -lx SBeach >> check.log
tail -5 "$HOME/Library/Logs/SBeach.log" >> check.log
