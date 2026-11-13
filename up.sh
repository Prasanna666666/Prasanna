#!/bin/bash
# Start Atlas: everything, with one command. Needs Docker Desktop and Ollama running.
#   ./up.sh                    start (it rebuilds only when the code changed since the last build)
#   ATLAS_NO_MAIL=1 ./up.sh    without reading Apple Mail
#   ./update.sh                get the newest version, then start
#   ATLAS_REBUILD=1 ./up.sh    rebuild even if nothing changed
set -euo pipefail
cd "$(dirname "$0")"
BUILT="$HOME/.atlas-built"
HERE="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
if [ "${ATLAS_REBUILD:-}" != 1 ] && [ "${ATLAS_NO_BUILD:-}" != 1 ] && [ "$HERE" != unknown ] && [ "$(cat "$BUILT" 2>/dev/null || true)" = "$HERE" ]; then
  export ATLAS_NO_BUILD=1   # the images are already built from this version: starting takes seconds
  echo "Nothing changed since the last build: starting without rebuilding."
fi
finance/scripts/up.sh
library/scripts/up.sh
atlas/up.sh
[ "${ATLAS_NO_BUILD:-}" = 1 ] || { [ "$HERE" = unknown ] || echo "$HERE" > "$BUILT"; }
scripts/make-apps.sh || true   # the Atlas and Stop Atlas apps in ~/Applications (only what is missing)
echo
echo "Atlas is ready: http://atlas.localhost:8000   (press Read new files there once; stop everything with the Stop Atlas app in ~/Applications)"
