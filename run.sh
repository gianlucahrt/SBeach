#!/bin/bash
# Startet SBeach direkt aus dem Quellcode (für Entwicklung).
set -euo pipefail
cd "$(dirname "$0")"
[[ -d .venv ]] || { echo "Bitte zuerst ./install.sh ausführen."; exit 1; }
source .venv/bin/activate
exec python -m sbeach
