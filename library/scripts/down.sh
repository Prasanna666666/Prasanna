#!/bin/bash
# Stop Documents. Your data stays in its Docker volume (nothing is deleted).
cd "$(dirname "$0")/.."
export PLATFORM_KEY="${PLATFORM_KEY:-stopping}" ATLAS_DB_KEY="${ATLAS_DB_KEY:-stopping}"  # stopping needs no keys, but compose insists on a value
docker compose down
scripts/apple-ocr.sh stop 2>/dev/null || true   # Apple's text recognition and its memory disk
