#!/bin/bash
# Run any Aperture command that reads your photos, in the sandbox, with the Mac kept awake. Short on purpose, so it pastes cleanly:
#   scripts/aperture-run.sh scan
#   scripts/aperture-run.sh venues --hours 1
#   scripts/aperture-run.sh judge --calibrate 60 --hours 1
cd "$(dirname "$0")/.."
export AP_ROOT="${AP_ROOT:-/Volumes/Expansion/Aperture}"
exec caffeinate -i scripts/aperture-sandboxed.sh "${PHOTO_DIR:-/Volumes/Expansion}" -- .venv/bin/aperture "$@"
