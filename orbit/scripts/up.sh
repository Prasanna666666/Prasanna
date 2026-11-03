#!/bin/bash
# Start Orbit. The database key lives in the macOS Keychain (created on first run) and is handed to Docker as a secret.
#   ./scripts/up.sh            start / rebuild
#   ./scripts/up.sh --show-key print the key once so you can back it up (lose the key = lose the data)
set -euo pipefail
cd "$(dirname "$0")/.."
SERVICE=orbit-db-key
if [ "${1:-}" = "--show-key" ]; then security find-generic-password -a "$USER" -s "$SERVICE" -w; exit 0; fi
[ "$(uname)" = "Darwin" ] || { echo "This script uses the macOS Keychain. On Linux export ORBIT_DB_KEY yourself."; exit 2; }
if ! KEY="$(security find-generic-password -a "$USER" -s "$SERVICE" -w 2>/dev/null)"; then
  KEY="$(openssl rand -base64 32)"
  security add-generic-password -a "$USER" -s "$SERVICE" -w "$KEY" -T "" -U
  echo "Created a new database key in your Keychain ('$SERVICE')."
  echo "BACK IT UP NOW:  ./scripts/up.sh --show-key   (store it somewhere safe, offline). Without it the data cannot be recovered."
fi
mkdir -p "$HOME/OrbitInbox/notes"
export ORBIT_DB_KEY="$KEY"
docker compose up -d --build
echo "Orbit: http://127.0.0.1:8501   (drop files into ~/OrbitInbox; the parser picks them up)"
