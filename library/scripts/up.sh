#!/bin/bash
# Start Documents: the one reader and store for every file and mail. The database key lives in the macOS Keychain (created on first run); you never type it.
#   ./scripts/up.sh            start / rebuild
#   ./scripts/up.sh --show-key print the key once so you can back it up (lose the key = lose the documents' index; your original files are untouched)
set -euo pipefail
cd "$(dirname "$0")/.."
source ../scripts/folders.sh   # first: the old folder names are renamed before anything creates the new ones
SERVICE=library-db-key
read_key() { security find-generic-password -a "$USER" -s "$SERVICE" -w 2>/dev/null; }
if [ "${1:-}" = "--show-key" ]; then read_key; exit 0; fi
[ "$(uname)" = "Darwin" ] || { echo "This script uses the macOS Keychain. On Linux export ATLAS_DB_KEY yourself."; exit 2; }
if ! KEY="$(read_key)"; then
  KEY="$(openssl rand -base64 32)"
  security add-generic-password -a "$USER" -s "$SERVICE" -w "$KEY" -T /usr/bin/security -U
  echo "Created a new database key in your Keychain ('$SERVICE'). Back it up: ./scripts/up.sh --show-key"
fi
mkdir -p "$HOME/AtlasInbox"
export ATLAS_FINANCE_DIR="${ATLAS_FINANCE_DIR:-$HOME/AtlasFinance}"   # keep your finance folder where it is: ATLAS_FINANCE_DIR=/path ./scripts/up.sh
mkdir -p "$ATLAS_FINANCE_DIR"
export ATLAS_DB_KEY="$KEY"
source ../scripts/platform-key.sh
FILES=(-f docker-compose.yml)
[ -d "${ATLAS_MAIL_DIR:-$HOME/Library/Mail}" ] && [ "${ATLAS_NO_MAIL:-}" != 1 ] && FILES+=(-f docker-compose.mail.yml)   # the Update button also reads Apple Mail (ATLAS_NO_MAIL=1 to turn off)
[ -d "${APERTURE_HOST_DRIVE:-/Volumes/Expansion}/Photos" ] && FILES+=(-f docker-compose.pictures.yml)   # pictures too, when the photo drive is connected
docker compose -p library down --remove-orphans >/dev/null 2>&1 || true   # containers of the earlier name hold the same port; the volumes stay
docker compose "${FILES[@]}" up -d --build
echo "Documents: http://documents.localhost:8502   (drop files into ~/AtlasInbox; finance files go in $ATLAS_FINANCE_DIR; mail is read from Apple Mail, read-only)"
