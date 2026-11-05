#!/bin/bash
# Start Orbit. The database key lives in the macOS Keychain (created on first run) and is handed to the app container as an environment variable (a Docker secret cannot be used with a read-only container).
#   ./scripts/up.sh            start / rebuild
#   ./scripts/up.sh --show-key print the key once so you can back it up (lose the key = lose the data)
set -euo pipefail
cd "$(dirname "$0")/.."
OLD=orbit-db-key        # first version of the entry: macOS asked for your password every time it was read
SERVICE=orbit-db-key-v2 # same key, readable by the `security` tool without a prompt
read_key() { security find-generic-password -a "$USER" -s "$1" -w 2>/dev/null; }
if [ "${1:-}" = "--show-key" ]; then read_key "$SERVICE" || read_key "$OLD"; exit 0; fi
[ "$(uname)" = "Darwin" ] || { echo "This script uses the macOS Keychain. On Linux export ORBIT_DB_KEY yourself."; exit 2; }
if ! KEY="$(read_key "$SERVICE")"; then
  if KEY="$(read_key "$OLD")"; then   # one last password prompt: copy the SAME key to the new entry, check it, and only then drop the old one
    security add-generic-password -a "$USER" -s "$SERVICE" -w "$KEY" -T /usr/bin/security -U
    [ "$(read_key "$SERVICE")" = "$KEY" ] || { echo "Could not copy the key safely; nothing was changed."; exit 1; }
    security delete-generic-password -a "$USER" -s "$OLD" >/dev/null 2>&1 || true
    echo "Moved your database key to a Keychain entry that no longer asks for your password."
  else
    KEY="$(openssl rand -base64 32)"
    security add-generic-password -a "$USER" -s "$SERVICE" -w "$KEY" -T /usr/bin/security -U
    echo "Created a new database key in your Keychain ('$SERVICE')."
    echo "BACK IT UP NOW:  ./scripts/up.sh --show-key   (store it somewhere safe, offline). Without it the data cannot be recovered."
  fi
fi
TOKSERVICE=orbit-web-token   # the secret in the link below: without it, other programs on this Mac cannot talk to Orbit's port
if ! TOKEN="$(read_key "$TOKSERVICE")"; then
  TOKEN="$(openssl rand -hex 24)"
  security add-generic-password -a "$USER" -s "$TOKSERVICE" -w "$TOKEN" -T /usr/bin/security -U
fi
export ORBIT_TOKEN="$TOKEN"
mkdir -p "$HOME/OrbitInbox/notes"
export ORBIT_FINANCE_DIR="${ORBIT_FINANCE_DIR:-$HOME/OrbitFinance}"   # keep your finance folder where it is: ORBIT_FINANCE_DIR=/path ./scripts/up.sh
mkdir -p "$ORBIT_FINANCE_DIR"
export ORBIT_DB_KEY="$KEY"
docker compose up -d --build
echo "Orbit: http://127.0.0.1:8501/?k=$TOKEN   (open THIS link once per browser; drop files into ~/OrbitInbox; finance files are read from $ORBIT_FINANCE_DIR, read-only)"
