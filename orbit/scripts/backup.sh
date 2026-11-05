#!/bin/bash
# Copy Finance's backups out of the container to a folder you choose (an external drive, for example).
# They stay encrypted with your database key, so the copy is safe to keep anywhere; without the key (./scripts/up.sh --show-key) it cannot be opened.
#   ./scripts/backup.sh /Volumes/MyDrive/orbit-backups
set -euo pipefail
cd "$(dirname "$0")/.."
[ -n "${1:-}" ] || { echo "Usage: ./scripts/backup.sh <folder>"; exit 2; }
mkdir -p "$1"
docker compose cp app:/data/backups/. "$1"
echo "Copied $(ls "$1" | wc -l | tr -d ' ') backup file(s) to $1"
