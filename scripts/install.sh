#!/usr/bin/env bash
# One-time setup. Everything (environment, models, data) goes on the external drive.
set -euo pipefail
DRIVE="${APERTURE_DRIVE:-/Volumes/Expansion}"
[ -d "$DRIVE" ] || { echo "Drive $DRIVE not found. Connect it first."; exit 1; }
PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 10))' || { echo "Python 3.10+ required (set PYTHON=...)"; exit 1; }
VENV="$DRIVE/Aperture/venv"
mkdir -p "$DRIVE/Aperture"
"$PY" -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -e "$(cd "$(dirname "$0")/.." && pwd)[ml,mac,ui]"
export APERTURE_DRIVE="$DRIVE"
"$VENV/bin/aperture" fetch-models
"$VENV/bin/aperture" install-launcher
"$VENV/bin/aperture" doctor || true
echo "Done. Open ~/Applications/Aperture.app"
