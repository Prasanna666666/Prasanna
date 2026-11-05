#!/bin/bash
# Start Photos in Docker (no internet, photos read-only). Needs Ollama running on the Mac. Open http://127.0.0.1:8765
set -euo pipefail
cd "$(dirname "$0")/.."
source ../scripts/platform-key.sh
# The picture index is encrypted with the key Documents keeps in the Keychain (start Documents first: library/scripts/up.sh).
if [ "$(uname)" = "Darwin" ]; then
  ORBIT_DB_KEY="$(security find-generic-password -a "$USER" -s library-db-key -w 2>/dev/null)" || { echo "Start Documents first: library/scripts/up.sh"; exit 1; }
  export ORBIT_DB_KEY
fi
docker compose -f docker-compose.aperture.yml up -d --build
echo "Photos: http://127.0.0.1:8765   (stop: docker compose -f docker-compose.aperture.yml down)"
