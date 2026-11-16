#!/bin/bash
# Start Atlas: everything, with one command. Needs Docker Desktop and Ollama running.
#   ./up.sh                    start (it rebuilds only when the code changed since the last build)
#   ATLAS_NO_MAIL=1 ./up.sh    without reading Apple Mail
#   ./update.sh                get the newest version, then start
#   ATLAS_REBUILD=1 ./up.sh    rebuild even if nothing changed
set -euo pipefail
cd "$(dirname "$0")"
# Make the most of the Apple chip: Ollama runs on the Mac's GPU already; these settings make it faster and lighter on memory (flash attention, and a smaller memory for what it has just read).
if [ "$(uname)" = Darwin ] && [ "$(launchctl getenv OLLAMA_FLASH_ATTENTION 2>/dev/null)" != 1 ]; then
  launchctl setenv OLLAMA_FLASH_ATTENTION 1 && launchctl setenv OLLAMA_KV_CACHE_TYPE q8_0 \
    && echo "Speed settings for the AI model are set. Quit and reopen Ollama once for them to apply."
fi
BUILT="$HOME/.atlas-built"
HERE="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
export ATLAS_BUILD="${HERE:0:7}"   # shown on the home page, so a part that was not updated can be seen
if [ "${ATLAS_REBUILD:-}" != 1 ] && [ "${ATLAS_NO_BUILD:-}" != 1 ] && [ "$HERE" != unknown ] && [ "$(cat "$BUILT" 2>/dev/null || true)" = "$HERE" ]; then
  export ATLAS_NO_BUILD=1   # the images are already built from this version: starting takes seconds
  echo "Nothing changed since the last build: starting without rebuilding."
fi
finance/scripts/up.sh
library/scripts/up.sh
atlas/up.sh
[ "${ATLAS_NO_BUILD:-}" = 1 ] || { [ "$HERE" = unknown ] || echo "$HERE" > "$BUILT"; }
scripts/make-apps.sh || true   # the Atlas and Stop Atlas apps in ~/Applications (only what is missing)
scripts/install-auto-read.sh || true   # the idle check that reads new files by itself when the Mac is idle and plugged in (fewer than 50 files; off: touch ~/.atlas-auto-off)
echo
echo "Atlas is ready: http://atlas.localhost:8000   (press Read new files there once; stop everything with the Stop Atlas app in ~/Applications)"
