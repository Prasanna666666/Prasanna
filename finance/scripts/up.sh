#!/bin/bash
# Start Finance. The database key lives in the macOS Keychain (created on first run) and is handed to the app container as an environment variable (a Docker secret cannot be used with a read-only container).
#   ./scripts/up.sh            start / rebuild
#   ./scripts/up.sh --show-key print the key once so you can back it up (lose the key = lose the data)
set -euo pipefail
cd "$(dirname "$0")/.."
source ../scripts/folders.sh   # first: the old folder names are renamed before anything creates the new ones
SERVICE=finance-db-key
OLDER=(orbit-db-key-v2 orbit-db-key)   # the entries from when Finance was called Orbit: read once, copied, never deleted
read_key() { security find-generic-password -a "$USER" -s "$1" -w 2>/dev/null; }
if [ "${1:-}" = "--show-key" ]; then read_key "$SERVICE" || read_key "${OLDER[0]}" || read_key "${OLDER[1]}"; exit 0; fi
[ "$(uname)" = "Darwin" ] || { echo "This script uses the macOS Keychain. On Linux export ATLAS_DB_KEY yourself."; exit 2; }
if ! KEY="$(read_key "$SERVICE")"; then
  KEY=""
  for old in "${OLDER[@]}"; do KEY="$(read_key "$old")" && break || KEY=""; done
  if [ -n "$KEY" ]; then   # the SAME key under the new name; the old entry stays as a spare
    security add-generic-password -a "$USER" -s "$SERVICE" -w "$KEY" -T /usr/bin/security -U
    [ "$(read_key "$SERVICE")" = "$KEY" ] || { echo "Could not copy the key safely; nothing was changed."; exit 1; }
    echo "Copied your database key to a Keychain entry named for Finance (the old entry is kept)."
  else
    KEY="$(openssl rand -base64 32)"
    security add-generic-password -a "$USER" -s "$SERVICE" -w "$KEY" -T /usr/bin/security -U
    echo "Created a new database key in your Keychain ('$SERVICE')."
    echo "BACK IT UP NOW:  ./scripts/up.sh --show-key   (store it somewhere safe, offline). Without it the data cannot be recovered."
  fi
fi
# No login password: this is your own laptop. (A password you set earlier is removed from the Keychain.) The database is still encrypted, with a key kept for you in the Keychain, so you never type anything.
security delete-generic-password -a "$USER" -s orbit-web-token >/dev/null 2>&1 || true
export ATLAS_TOKEN=""
mkdir -p "$HOME/AtlasInbox/notes"
export ATLAS_DB_KEY="$KEY"
source ../scripts/platform-key.sh
# Finance used to be called Orbit: stop its old containers (they hold the same port). The volume with your database is NOT removed and is reused.
docker compose -p orbit down --remove-orphans >/dev/null 2>&1 || true
# The database lives in a volume that used to be called orbit_orbit-data: it is COPIED into the new one (the old one is kept until you delete it yourself).
if docker volume inspect orbit_orbit-data >/dev/null 2>&1 && ! docker volume inspect finance_finance-data >/dev/null 2>&1; then
  docker volume create finance_finance-data >/dev/null
  docker run --rm --entrypoint sh -v orbit_orbit-data:/from:ro -v finance_finance-data:/to alpine/socat:1.8.0.0 -c 'cp -a /from/. /to/ && ls /to'
  echo "Copied your Finance data to the new volume. The old one (orbit_orbit-data) is untouched: delete it with 'docker volume rm orbit_orbit-data' once all is well."
fi
docker compose up -d --build
echo "Finance: http://finance.localhost:8501   (no password; files and mail are read by Documents: ../library/scripts/up.sh)"
