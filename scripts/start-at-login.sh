#!/bin/bash
# Runs by itself when you log in (installed by ./scripts/install-autostart.sh): starts Docker and Ollama if they are not running, waits for them, then brings Atlas up.
# Containers also restart on their own whenever Docker starts; this makes sure of it and picks up any change.
cd "$(dirname "$0")/.."
say() { echo "$(date '+%F %T') $*"; }
pgrep -x Ollama >/dev/null || { say "starting Ollama"; open -ga Ollama 2>/dev/null || true; }
docker info >/dev/null 2>&1 || { say "starting Docker"; open -ga Docker; }
for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 5; done
docker info >/dev/null 2>&1 || { say "Docker did not start in time"; exit 1; }
say "starting Atlas"
./up.sh
say "Atlas is up: http://atlas.localhost:8000"
