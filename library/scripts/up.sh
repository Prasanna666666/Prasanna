#!/bin/bash
# Start Documents: the one reader and store for every file and mail. The database key lives in the macOS Keychain (created on first run); you never type it.
#   ./scripts/up.sh            start / rebuild
#   ./scripts/up.sh --show-key print the key once so you can back it up (lose the key = lose the documents' index; your original files are untouched)
set -euo pipefail
cd "$(dirname "$0")/.."
SERVICE=library-db-key
read_key() { security find-generic-password -a "$USER" -s "$SERVICE" -w 2>/dev/null; }
if [ "${1:-}" = "--show-key" ]; then read_key; exit 0; fi
[ "$(uname)" = "Darwin" ] || { echo "This script uses the macOS Keychain. On Linux export ORBIT_DB_KEY yourself."; exit 2; }
if ! KEY="$(read_key)"; then
  KEY="$(openssl rand -base64 32)"
  security add-generic-password -a "$USER" -s "$SERVICE" -w "$KEY" -T /usr/bin/security -U
  echo "Created a new database key in your Keychain ('$SERVICE'). Back it up: ./scripts/up.sh --show-key"
fi
mkdir -p "$HOME/OrbitInbox"
export ORBIT_FINANCE_DIR="${ORBIT_FINANCE_DIR:-$HOME/OrbitFinance}"   # keep your finance folder where it is: ORBIT_FINANCE_DIR=/path ./scripts/up.sh
mkdir -p "$ORBIT_FINANCE_DIR"
export ORBIT_DB_KEY="$KEY"
source ../scripts/platform-key.sh
FILES=(-f docker-compose.yml)
[ -d "${ORBIT_MAIL_DIR:-$HOME/Library/Mail}" ] && [ "${ORBIT_NO_MAIL:-}" != 1 ] && FILES+=(-f docker-compose.mail.yml)   # the Update button also reads Apple Mail (ORBIT_NO_MAIL=1 to turn off)
[ -d "${APERTURE_HOST_DRIVE:-/Volumes/Expansion}/Photos" ] && FILES+=(-f docker-compose.pictures.yml)   # pictures too, when the photo drive is connected
docker compose "${FILES[@]}" up -d --build
echo "Documents: http://documents.localhost:8502   (drop files into ~/OrbitInbox; finance files go in $ORBIT_FINANCE_DIR; mail is read from Apple Mail, read-only)"
