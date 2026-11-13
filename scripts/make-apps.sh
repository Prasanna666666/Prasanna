#!/bin/bash
# Makes two double-clickable apps in ~/Applications (Mac): "Atlas" switches Atlas on if it is off and opens it, "Stop Atlas" stops everything (nothing is deleted).
# They are made again whenever this script changes, so an older copy never stays behind.
set -euo pipefail
[ "$(uname)" = "Darwin" ] || exit 0
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
APPS="$HOME/Applications"
mkdir -p "$APPS"
PATHS="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/Applications/Docker.app/Contents/Resources/bin"
VERSION="$(shasum "$0" | cut -c1-12)"
if [ "$(cat "$APPS/.atlas-apps-version" 2>/dev/null || true)" != "$VERSION" ]; then
  rm -rf "$APPS/Atlas.app" "$APPS/Stop Atlas.app"   # only our own two apps
fi
[ -d "$APPS/Atlas.app" ] || osacompile -o "$APPS/Atlas.app" \
  -e "do shell script \"export PATH=$PATHS; docker ps --format '{{.Names}}' | grep -q atlas-documents-app-1 || (ATLAS_NO_MAIL=1 ATLAS_LOGIN_DELAY=0 '$ROOT/scripts/start-at-login.sh' >/dev/null 2>&1 &)\"" \
  -e 'delay 2' \
  -e 'open location "http://atlas.localhost:8000"'
[ -d "$APPS/Stop Atlas.app" ] || osacompile -o "$APPS/Stop Atlas.app" \
  -e "do shell script \"export PATH=$PATHS; \" & quoted form of \"$ROOT/down.sh\"" \
  -e 'display notification "Atlas is stopped. Open the Atlas app to switch it on again." with title "Atlas"'
echo "$VERSION" > "$APPS/.atlas-apps-version"
