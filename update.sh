#!/bin/bash
# Get the newest Atlas and start it: one command.   ./update.sh      (ATLAS_NO_MAIL=1 ./update.sh without mail)
set -euo pipefail
cd "$(dirname "$0")"
git fetch origin
git checkout -B atlas origin/atlas
exec ./up.sh
