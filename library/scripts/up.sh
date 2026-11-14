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
../scripts/folders-compose.sh docker-compose.folders.yml   # your category folders and any extra folders listed in ~/AtlasFolders.txt, read-only
FILES=(-f docker-compose.yml -f docker-compose.folders.yml)
[ -d "${ATLAS_MAIL_DIR:-$HOME/Library/Mail}" ] && [ "${ATLAS_NO_MAIL:-}" != 1 ] && FILES+=(-f docker-compose.mail.yml)   # the Update button also reads Apple Mail (ATLAS_NO_MAIL=1 to turn off)
DRIVE="${APERTURE_HOST_DRIVE:-}"   # the drive that holds the photos: named by you, or the first connected drive that has a Photos folder and the picture models (Aperture/models)
if [ -z "$DRIVE" ]; then
  for volume in /Volumes/*/; do
    [ -d "${volume}Photos" ] && [ -d "${volume}Aperture/models" ] && DRIVE="${volume%/}" && break
  done
fi
if [ -n "$DRIVE" ] && [ -d "$DRIVE/Photos" ]; then
  export APERTURE_HOST_DRIVE="$DRIVE"
  FILES+=(-f docker-compose.pictures.yml)   # pictures too, when the photo drive is connected
else
  echo "Photos: no connected drive with a Photos folder and Aperture/models was found. Plug it in and run ./up.sh again (or set APERTURE_HOST_DRIVE=/Volumes/<name>)."
fi
if [ ! -f "$HOME/.atlas-migrated-documents" ]; then   # containers of the earlier name hold the same port; the volumes stay (once)
  docker compose -p library down --remove-orphans >/dev/null 2>&1 || true
  touch "$HOME/.atlas-migrated-documents"
fi
docker compose "${FILES[@]}" up -d $([ "${ATLAS_NO_BUILD:-}" = 1 ] || echo --build)   # ATLAS_NO_BUILD=1: start what is already built
echo "Folders read (read-only): ~/AtlasInbox, $ATLAS_FINANCE_DIR, ~/AtlasHealth, ~/AtlasTravel and the ones listed in ~/AtlasFolders.txt. Mail is read from Apple Mail, read-only."
