#!/bin/bash
# Add a folder for Atlas to read, in place and READ-ONLY (your originals are never changed or moved): iCloud Drive folders, for example.
#   scripts/add-folder.sh            a window opens: choose the kind of documents, then the folder
#   scripts/add-folder.sh health "/path/to/folder"       without windows
# Nothing here is sent anywhere: the path is written only to ~/AtlasFolders.txt on this Mac.
set -euo pipefail
cd "$(dirname "$0")/.."
LIST="${ATLAS_FOLDERS_FILE:-$HOME/AtlasFolders.txt}"
category="${1:-}"; folder="${2:-}"
if [ -z "$category" ]; then
  category="$(osascript -e 'choose from list {"finance","health","travel","personal","others","documents"} with prompt "What kind of documents are in the folder?" default items {"personal"}' 2>/dev/null || true)"
  [ -n "$category" ] && [ "$category" != "false" ] || { echo "Cancelled."; exit 1; }
fi
if [ -z "$folder" ]; then
  folder="$(osascript -e 'POSIX path of (choose folder with prompt "Choose the folder Atlas should read (read-only)")' 2>/dev/null || true)"
  [ -n "$folder" ] || { echo "Cancelled."; exit 1; }
fi
folder="${folder%/}"
fail() { echo "Not added: $*" >&2; exit 1; }
[[ "$category" =~ ^[a-z]{2,20}$ ]] && [ "$category" != "mail" ] || fail "the kind must be one lowercase word (finance, health, travel, personal, others ...), not 'mail'"
[ -d "$folder" ] || fail "that folder does not exist: $folder"
[[ "$folder" == *\"* || "$folder" == *:* || "$folder" == *\\* ]] && fail "the folder path may not contain a colon, quote or backslash"
[ -f "$LIST" ] || scripts/folders-compose.sh /dev/null   # creates the list with its explanation
real="$(cd "$folder" && pwd -P)"
already=0
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ""|\#*) continue ;; esac
  path="${line#*=}"; path="${path/#\~/$HOME}"; path="${path%/}"
  if [ -d "$path" ] && [ "$(cd "$path" && pwd -P)" = "$real" ]; then already=1; fi
done < "$LIST"
if [ "$already" = 1 ]; then echo "Already added: $folder"; else echo "$category=$folder" >> "$LIST"; echo "Added: $category = $folder"; fi
files="$(find "$folder" -type f ! -name '.*' 2>/dev/null | wc -l | tr -d ' ')"
cloud="$(find "$folder" -type f -name '.*.icloud' 2>/dev/null | wc -l | tr -d ' ')"
echo "Found $files files you can read now."
[ "$cloud" = 0 ] || echo "$cloud more are only in iCloud, not on this Mac yet: in Finder, right-click the folder and choose Download Now, then they can be read."
if [ "${ATLAS_SKIP_APPLY:-}" = 1 ]; then exit 0; fi
if command -v docker >/dev/null 2>&1 && ! docker run --rm --entrypoint ls -v "$folder:/probe:ro" alpine/socat:1.8.0.0 /probe >/dev/null 2>&1; then
  echo "Docker cannot open that folder yet. Give it permission once: System Settings, Privacy and Security, Full Disk Access, switch on Docker, then quit and reopen Docker Desktop, and run this again." >&2
  exit 2
fi
echo "Docker can read it (read-only). Restarting the reader so it takes the folder ..."
ATLAS_NO_BUILD=1 library/scripts/up.sh
echo "Done. Press Read new files in Atlas."
