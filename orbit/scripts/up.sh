#!/bin/bash
# Start Finance. The database key lives in the macOS Keychain (created on first run) and is handed to the app container as an environment variable (a Docker secret cannot be used with a read-only container).
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
# No login password: this is your own laptop. (A password you set earlier is removed from the Keychain.) The database is still encrypted, with a key kept for you in the Keychain, so you never type anything.
security delete-generic-password -a "$USER" -s orbit-web-token >/dev/null 2>&1 || true
export ORBIT_TOKEN=""
mkdir -p "$HOME/OrbitInbox/notes"
export ORBIT_FINANCE_DIR="${ORBIT_FINANCE_DIR:-$HOME/OrbitFinance}"   # keep your finance folder where it is: ORBIT_FINANCE_DIR=/path ./scripts/up.sh
mkdir -p "$ORBIT_FINANCE_DIR"
export ORBIT_DB_KEY="$KEY"
FILES=(-f docker-compose.yml)
[ -d "${ORBIT_MAIL_DIR:-$HOME/Library/Mail}" ] && [ "${ORBIT_NO_MAIL:-}" != 1 ] && FILES+=(-f docker-compose.mail.yml)   # the Update button also reads Apple Mail (ORBIT_NO_MAIL=1 to turn off)
docker compose "${FILES[@]}" up -d --build
echo "Finance: http://finance.localhost:8501   (no password; drop files into ~/OrbitInbox; finance files are read from $ORBIT_FINANCE_DIR, read-only)"
