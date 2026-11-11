#!/bin/bash
# Start Atlas: everything, with one command. Needs Docker Desktop and Ollama running.
#   ./up.sh                    start / rebuild all of it
#   ATLAS_NO_MAIL=1 ./up.sh    without reading Apple Mail
#   LIBRARY_INBOX_MODE=rw ./up.sh   also allow filing documents into folders (off by default)
set -euo pipefail
cd "$(dirname "$0")"
finance/scripts/up.sh
library/scripts/up.sh
atlas/up.sh
echo
echo "Atlas is ready: http://atlas.localhost:8000   (press Read new files there once; stop everything with ./down.sh)"
