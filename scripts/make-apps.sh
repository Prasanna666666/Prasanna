#!/bin/bash
# Makes two double-clickable apps in ~/Applications (Mac): "Atlas" opens Atlas, "Stop Atlas" stops everything (nothing is deleted). Only creates what is missing.
set -euo pipefail
[ "$(uname)" = "Darwin" ] || exit 0
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APPS="$HOME/Applications"
mkdir -p "$APPS"
PATHS="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/Applications/Docker.app/Contents/Resources/bin"
[ -d "$APPS/Atlas.app" ] || osacompile -o "$APPS/Atlas.app" -e 'open location "http://atlas.localhost:8000"'
[ -d "$APPS/Stop Atlas.app" ] || osacompile -o "$APPS/Stop Atlas.app" \
  -e "do shell script \"export PATH=$PATHS; \" & quoted form of \"$ROOT/down.sh\"" \
  -e 'display notification "Atlas is stopped. Open the Atlas app, or log in again, to start it." with title "Atlas"'
