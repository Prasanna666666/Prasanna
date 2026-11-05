#!/bin/bash
# Start Home. Needs Docker. Open http://home.localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
docker compose up -d --build
echo "Home: http://home.localhost:${HUB_PORT:-8000}   (stop: ./down.sh)"
