#!/bin/bash
# One-off: copy an existing Aperture index from the drive into the private Docker volume `aperture-data`.
# Nothing is deleted. After you have checked the app works, remove the old folder yourself (it is not protected):
#   rm -r /Volumes/Expansion/Aperture/data
set -euo pipefail
DRIVE="${APERTURE_HOST_DRIVE:-/Volumes/Expansion}"
[ -d "$DRIVE/Aperture/data" ] || { echo "no $DRIVE/Aperture/data to copy"; exit 1; }
docker volume create aperture-data >/dev/null
docker run --rm --network none -v "$DRIVE/Aperture/data:/from:ro" -v aperture-data:/to alpine:3.20 sh -c 'cp -a /from/. /to/ && chmod 700 /to && ls /to | head'
echo "copied into the volume. Start with: docker compose -f docker-compose.aperture.yml up -d"
