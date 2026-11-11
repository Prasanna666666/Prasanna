#!/bin/bash
# Runs by itself when you log in (installed by ./scripts/install-autostart.sh). It waits a little so the computer finishes starting first, starts Docker and Ollama
# if they are not running, and only if Atlas did not come back by itself (the containers restart with Docker) brings it up, without rebuilding anything.
cd "$(dirname "$0")/.."
say() { echo "$(date '+%F %T') $*"; }
sleep "${ATLAS_LOGIN_DELAY:-45}"
pgrep -x Ollama >/dev/null || { say "starting Ollama"; open -ga Ollama 2>/dev/null || true; }
docker info >/dev/null 2>&1 || { say "starting Docker"; open -ga Docker; }
for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 5; done
docker info >/dev/null 2>&1 || { say "Docker did not start in time"; exit 1; }
for _ in $(seq 1 12); do docker ps --format '{{.Names}}' | grep -q '^atlas-atlas-1$' && break; sleep 5; done
if docker ps --format '{{.Names}}' | grep -q '^atlas-atlas-1$'; then
  say "Atlas came back by itself: http://atlas.localhost:8000"
else
  say "starting Atlas (no rebuild)"
  ATLAS_NO_BUILD=1 ./up.sh
  say "Atlas is up: http://atlas.localhost:8000"
fi
