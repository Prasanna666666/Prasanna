#!/bin/bash
# Start Photos in Docker (no internet, photos read-only). Needs Ollama running on the Mac. Open http://127.0.0.1:8765
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f docker-compose.aperture.yml up -d --build
echo "Photos: http://127.0.0.1:8765   (stop: docker compose -f docker-compose.aperture.yml down)"
