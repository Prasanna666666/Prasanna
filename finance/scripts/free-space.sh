#!/bin/bash
# Keep only the Ministral model in Ollama and delete the others (asks first; nothing is removed without your "y").
#   ./scripts/free-space.sh          review and confirm
#   ./scripts/free-space.sh --dry    only show what would be removed
# Safety: refuses to remove anything unless a Ministral model is already installed, so you never end up with zero models.
set -euo pipefail
KEEP='^ministral'
DRY=0; [ "${1:-}" = "--dry" ] && DRY=1

command -v ollama >/dev/null || { echo "ollama not found. Install the Ollama app first."; exit 2; }
ollama list >/dev/null 2>&1 || { echo "Ollama is not running. Open the Ollama app and try again."; exit 2; }

echo "Installed models:"; ollama list; echo
NAMES="$(ollama list | awk 'NR>1 && $1 != "" {print $1}')"
KEEP_LIST="$(printf '%s\n' "$NAMES" | grep -E "$KEEP" || true)"
DEL_LIST="$(printf '%s\n' "$NAMES" | grep -Ev "$KEEP" | sed '/^$/d' || true)"

if [ -z "$KEEP_LIST" ]; then
  echo "No Ministral model is installed yet, so I will not delete anything."
  echo "Run:  ollama pull ministral-3:3b    (then run this script again)"
  exit 1
fi
echo "Keeping:";  printf '  %s\n' $KEEP_LIST
if [ -z "$DEL_LIST" ]; then echo "Nothing else to remove."; exit 0; fi
echo "Would remove:"; printf '  %s\n' $DEL_LIST
[ "$DRY" = 1 ] && exit 0

read -r -p "Remove these $(printf '%s\n' "$DEL_LIST" | wc -l | tr -d ' ') model(s)? [y/N] " ans
[ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "Cancelled. Nothing removed."; exit 0; }
printf '%s\n' "$DEL_LIST" | while read -r m; do [ -n "$m" ] && ollama rm "$m"; done
echo; echo "Done. Remaining models:"; ollama list
du -sh "${OLLAMA_MODELS:-$HOME/.ollama/models}" 2>/dev/null || true
