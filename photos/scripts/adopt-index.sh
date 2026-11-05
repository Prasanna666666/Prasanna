#!/bin/bash
# One time: copy the index you already have (the old Docker volume `aperture-data`) into `library-pictures`, so the pictures are not read again.
# Run it after the Documents service has been started once (library/scripts/up.sh creates the volume), and before the first Update.
set -euo pipefail
docker volume inspect aperture-data >/dev/null 2>&1 || { echo "No old index (aperture-data) found: nothing to copy."; exit 0; }
docker volume inspect library-pictures >/dev/null 2>&1 || { echo "Start Documents first: library/scripts/up.sh"; exit 1; }
docker run --rm -v aperture-data:/from:ro -v library-pictures:/to alpine sh -c 'cp -a /from/. /to/'
echo "Copied. The old volume aperture-data is untouched; remove it later with: docker volume rm aperture-data"
