#!/bin/bash
# Get the newest Atlas and start it: one command.   ./update.sh      (ATLAS_NO_MAIL=1 ./update.sh without mail)
# It refuses, and changes nothing, if you have unsaved changes or commits of your own on the branch (scripts/update-code.sh).
set -euo pipefail
cd "$(dirname "$0")"
scripts/update-code.sh
exec ./up.sh
