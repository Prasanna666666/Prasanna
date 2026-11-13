#!/bin/bash
# Writes a compose override that gives the reader your category folders (finance, health, travel) and any extra folders you list, all READ-ONLY, so the originals
# stay exactly where they are, in iCloud Drive for example. Usage: scripts/folders-compose.sh <output file>
set -euo pipefail
OUT="$1"
LIST="${ATLAS_FOLDERS_FILE:-$HOME/AtlasFolders.txt}"
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
names=("finance=/collections/finance")
mounts=()
n=0
seen_dirs=()
have=" "   # the categories the person has a folder for
real_of() { (cd "$1" 2>/dev/null && pwd -P) || echo "$1"; }
taken() { [[ " ${seen_dirs[*]:-} " == *" $1 "* ]]; }   # the same folder reached two ways is read once
[ -d "$HOME/AtlasHealth" ] && seen_dirs+=("$(real_of "$HOME/AtlasHealth")")
[ -d "$HOME/AtlasTravel" ] && seen_dirs+=("$(real_of "$HOME/AtlasTravel")")
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
  real="$(real_of "$path")"
  if taken "$real"; then echo "AtlasFolders.txt: $path is already read: taken once" >&2; continue; fi
  seen_dirs+=("$real")
  n=$((n + 1))
  have="$have$name "
  names+=("$name=/collections/$name-$n")
  mounts+=("$path:/collections/$name-$n:ro")
done < "$LIST"
# Folders found by their names, nothing to add by hand: finance, health, travel, personal and others (Dutch names too: financien, gezondheid, reizen, persoonlijk,
# overig, diversen ...), up to three levels deep in iCloud Drive, in ~/Documents and on the Desktop. A folder inside one already taken is not taken again.
canon() {
  case "$(echo "$1" | tr '[:upper:]' '[:lower:]')" in
    finance|finances|financien|financiën|financieel|financial) echo finance ;;
    health|gezondheid|medisch|medical) echo health ;;
    travel|travels|trips|reizen|reis) echo travel ;;
    personal|persoonlijk|prive|privé|private) echo personal ;;
    others|other|overig|overige|diversen|misc|miscellaneous|various) echo others ;;
    *) echo "" ;;
  esac
}
ICLOUD="${ATLAS_ICLOUD_DIR:-$HOME/Library/Mobile Documents/com~apple~CloudDocs}"
candidates=()
for root in "$ICLOUD" "$HOME/Documents" "$HOME/Desktop"; do
  [ -d "$root" ] || continue
  while IFS= read -r dir; do
    [ -n "$(canon "$(basename "$dir")")" ] && candidates+=("$dir")
  done < <(find "$root" -maxdepth 3 \( -name '.*' -o -name Library -o -name node_modules \) -prune -o -type d -print 2>/dev/null)
done
# the shallowest first, so a parent wins over what lies inside it
sorted=()
while IFS= read -r line; do sorted+=("${line#*|}"); done < <(for c in "${candidates[@]:-}"; do [ -n "$c" ] && echo "$(echo "$c" | tr -cd '/' | wc -c | tr -d ' ')|$c"; done | sort -t'|' -k1,1n -k2)
found=0
for dir in "${sorted[@]:-}"; do
  [ -n "$dir" ] || continue
  label="$(canon "$(basename "$dir")")"
  if [[ "$dir" == *\"* || "$dir" == *:* || "$dir" == *\\* ]]; then echo "Skipped $dir (the path may not contain a colon, quote or backslash)" >&2; continue; fi
  real="$(real_of "$dir")"
  taken "$real" && continue
  inside=0
  for t in "${seen_dirs[@]:-}"; do [ -n "$t" ] && [[ "$real/" == "$t/"* ]] && inside=1; done
  [ "$inside" = 1 ] && continue   # lies inside a folder already read
  [ "$found" -ge 20 ] && { echo "More than 20 category folders found: the rest are left out (list them in ~/AtlasFolders.txt to choose)" >&2; break; }
  found=$((found + 1))
  seen_dirs+=("$real")
  n=$((n + 1))
  have="$have$label "
  names+=("$label=/collections/$label-$n")
  mounts+=("$dir:/collections/$label-$n:ro")
  echo "Atlas will read (read-only): $dir as $label" >&2
done

# The default folders in the home folder (~/AtlasHealth, ~/AtlasTravel): used only when the person has no folder of that kind, or has put files in them
for kind in health travel; do
  default="$HOME/Atlas$(echo "${kind:0:1}" | tr '[:lower:]' '[:upper:]')${kind:1}"
  if [[ "$have" != *" $kind "* ]]; then mkdir -p "$default"; fi
  if [ -d "$default" ] && { [[ "$have" != *" $kind "* ]] || [ -n "$(ls -A "$default" 2>/dev/null)" ]; }; then
    names+=("$kind=/collections/$kind")
    mounts+=("$default:/collections/$kind:ro")
  fi
done
{
  echo "# Written by scripts/folders-compose.sh: do not edit (edit ~/AtlasFolders.txt instead)."
  echo "services:"
  echo "  parser:"
  echo "    environment:"
  printf '      LIBRARY_COLLECTIONS: "%s"\n' "$(IFS=,; echo "${names[*]}")"
  echo "    volumes:"
  for m in "${mounts[@]}"; do printf '      - "%s"\n' "$m"; done
} > "$OUT"
