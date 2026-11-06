#!/bin/bash
# One-off: copy an existing Aperture index from the drive into the private Docker volume `library-pictures` (the one Documents' indexer fills and Photos opens).
# An index already copied into the old volume `aperture-data` is moved the same way: set FROM_VOLUME=aperture-data.
# Nothing is deleted. After you have checked the app works, remove the old folder yourself (it is not protected):
#   rm -r /Volumes/Expansion/Aperture/data
set -euo pipefail
DRIVE="${APERTURE_HOST_DRIVE:-/Volumes/Expansion}"
SOURCE="$DRIVE/Aperture/data"
[ -n "${FROM_VOLUME:-}" ] && SOURCE="$FROM_VOLUME"
[ -d "$SOURCE" ] || docker volume inspect "$SOURCE" >/dev/null 2>&1 || { echo "no $SOURCE to copy"; exit 1; }
docker volume create library-pictures >/dev/null
docker run --rm --network none -v "$SOURCE:/from:ro" -v library-pictures:/to alpine:3.20 sh -c 'cp -a /from/. /to/ && chmod 700 /to && ls /to | head'
echo "copied into the volume. Start Documents (library/scripts/up.sh), then Photos (scripts/up.sh)"
