#!/bin/bash
# Start Atlas. Needs Docker. Open http://atlas.localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
source ../scripts/platform-key.sh
docker compose up -d --build
echo "Atlas: http://atlas.localhost:${ATLAS_PORT:-8000}   (stop: ./down.sh)"
