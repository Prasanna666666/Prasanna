#!/bin/bash
# Writes a compose override that gives the reader your category folders (finance, health, travel) and any extra folders you list, all READ-ONLY, so the originals
# stay exactly where they are, in iCloud Drive for example. Usage: scripts/folders-compose.sh <output file>
set -euo pipefail
OUT="$1"
LIST="${ATLAS_FOLDERS_FILE:-$HOME/AtlasFolders.txt}"
mkdir -p "$HOME/AtlasHealth" "$HOME/AtlasTravel"
if [ ! -f "$LIST" ]; then
  cat > "$LIST" <<'TXT'
# Extra folders Atlas reads. Read-only: your originals are never changed or moved.
# One per line:   category=/full/path/to/the/folder
# category is one lowercase word: finance, health, travel, or any name you like.
# Example, a health folder in iCloud Drive (remove the # to use it):
# health=/Users/yourname/Library/Mobile Documents/com~apple~CloudDocs/Health
# Docker needs permission for such a folder once: System Settings, Privacy and Security, Full Disk Access, Docker.
# Files that iCloud has only in the cloud (not downloaded to this Mac) cannot be read until you download them (right click, Download Now).
TXT
fi
names=("finance=/collections/finance" "health=/collections/health" "travel=/collections/travel")
mounts=("$HOME/AtlasHealth:/collections/health:ro" "$HOME/AtlasTravel:/collections/travel:ro")
n=0
# Folders found by their names: finance, health, travel, personal or others, at the top of iCloud Drive, inside its Atlas or Documents folder, in ~/Documents (or its Atlas
# folder) and on the Desktop (nothing to add by hand).
ICLOUD="${ATLAS_ICLOUD_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs}"
seen_dirs=()
for parent in "$ICLOUD" "$ICLOUD/Atlas" "$ICLOUD/Documents" "$HOME/Documents" "$HOME/Documents/Atlas" "$HOME/Desktop"; do
  [ -d "$parent" ] || continue
  for dir in "$parent"/*/; do
    [ -d "$dir" ] || continue
    dir="${dir%/}"
    label="$(basename "$dir" | tr '[:upper:]' '[:lower:]')"
    case "$label" in finance|health|travel|personal|others) ;; *) continue ;; esac
    if [[ "$dir" == *\"* || "$dir" == *:* || "$dir" == *\\* ]]; then echo "iCloud: skipped $dir (the path may not contain a colon, quote or backslash)" >&2; continue; fi
    real="$(cd "$dir" && pwd -P)"   # the same folder reached two ways (iCloud syncs Documents) is taken once
    if [[ " ${seen_dirs[*]:-} " == *" $real "* ]]; then continue; fi
    seen_dirs+=("$real")
    n=$((n + 1))
    names+=("$label=/collections/$label-$n")
    mounts+=("$dir:/collections/$label-$n:ro")
    echo "Atlas will read (read-only): $dir as $label" >&2
  done
done
while IFS= read -r line || [ -n "$line" ]; do
  line="${line#"${line%%[![:space:]]*}"}"
  case "$line" in ""|\#*) continue ;; esac
  name="${line%%=*}"; path="${line#*=}"
  name="$(echo "$name" | tr -d '[:space:]')"
  path="${path#"${path%%[![:space:]]*}"}"; path="${path%"${path##*[![:space:]]}"}"
  path="${path/#\~/$HOME}"
  if ! [[ "$name" =~ ^[a-z]{2,20}$ ]] || [ "$name" = "mail" ]; then echo "AtlasFolders.txt: skipped '$line' (the category must be one lowercase word, not 'mail')" >&2; continue; fi
  if [ ! -d "$path" ]; then echo "AtlasFolders.txt: skipped '$name': no such folder: $path" >&2; continue; fi
  if [[ "$path" == *\"* || "$path" == *:* || "$path" == *\\* || "$path" == *$'\t'* ]]; then echo "AtlasFolders.txt: skipped '$name': the path may not contain a colon, quote or backslash" >&2; continue; fi
  n=$((n + 1))
  names+=("$name=/collections/$name-$n")
  mounts+=("$path:/collections/$name-$n:ro")
done < "$LIST"
{
  echo "# Written by scripts/folders-compose.sh: do not edit (edit ~/AtlasFolders.txt instead)."
  echo "services:"
  echo "  parser:"
  echo "    environment:"
  printf '      LIBRARY_COLLECTIONS: "%s"\n' "$(IFS=,; echo "${names[*]}")"
  echo "    volumes:"
  for m in "${mounts[@]}"; do printf '      - "%s"\n' "$m"; done
} > "$OUT"
