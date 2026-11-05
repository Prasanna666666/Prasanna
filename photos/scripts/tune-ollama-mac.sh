#!/bin/bash
# Make Ollama lighter and steadier on an 8 GB Mac. Changes only Ollama's own server options (nothing in your data or photos).
#
#   scripts/tune-ollama-mac.sh --dry        show what would change, do nothing
#   scripts/tune-ollama-mac.sh              apply for this login session, then restart the Ollama app (asks first)
#   scripts/tune-ollama-mac.sh --persist    also keep it after a reboot (writes ~/Library/LaunchAgents/local.ollama-tune.plist)
#   scripts/tune-ollama-mac.sh --undo       remove the options (and the LaunchAgent) and restart Ollama
#
# What each option does:
#   OLLAMA_NUM_PARALLEL=1        one request at a time: the context memory is not multiplied
#   OLLAMA_MAX_LOADED_MODELS=1   never keep two models in RAM (Orbit + Aperture share one Ministral)
#   OLLAMA_FLASH_ATTENTION=1     less memory and a little faster attention
#   OLLAMA_KV_CACHE_TYPE=q8_0    the context cache takes about half the memory (needs flash attention)
#   OLLAMA_KEEP_ALIVE=2m         give the RAM back 2 minutes after the last request
set -euo pipefail
VARS=(OLLAMA_NUM_PARALLEL=1 OLLAMA_MAX_LOADED_MODELS=1 OLLAMA_FLASH_ATTENTION=1 OLLAMA_KV_CACHE_TYPE=q8_0 OLLAMA_KEEP_ALIVE=2m)
PLIST="$HOME/Library/LaunchAgents/local.ollama-tune.plist"
MODE="${1:-apply}"
run() { if [ "$MODE" = "--dry" ]; then echo "  would run: $*"; else "$@"; fi; }

case "$MODE" in --dry|apply|--persist|--undo) ;; *) sed -n '2,9p' "$0"; exit 2 ;; esac
if [ "$MODE" != "--dry" ] && [ "$(uname)" != "Darwin" ]; then echo "This is for macOS."; exit 2; fi

if [ "$MODE" != "--dry" ] && command -v ollama >/dev/null && [ -n "$(ollama ps 2>/dev/null | awk 'NR>1')" ]; then
  echo "A model is loaded right now:"; ollama ps
  read -r -p "Restarting Ollama will unload it. Continue? [y/N] " a
  [ "$a" = y ] || [ "$a" = Y ] || { echo "Cancelled. Nothing changed."; exit 0; }
fi

if [ "$MODE" = "--undo" ]; then
  for kv in "${VARS[@]}"; do run launchctl unsetenv "${kv%%=*}"; done
  run rm -f "$PLIST"
else
  for kv in "${VARS[@]}"; do run launchctl setenv "${kv%%=*}" "${kv#*=}"; done
  if [ "$MODE" = "--persist" ]; then
    if [ "$MODE" = "--dry" ]; then :; else
      mkdir -p "$(dirname "$PLIST")"
      {
        echo '<?xml version="1.0" encoding="UTF-8"?>'
        echo '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        echo '<plist version="1.0"><dict><key>Label</key><string>local.ollama-tune</string><key>RunAtLoad</key><true/>'
        echo '<key>ProgramArguments</key><array><string>/bin/sh</string><string>-c</string><string>'
        for kv in "${VARS[@]}"; do printf 'launchctl setenv %s %s; ' "${kv%%=*}" "${kv#*=}"; done
        echo '</string></array></dict></plist>'
      } > "$PLIST"
      echo "Wrote $PLIST (remove it with --undo)."
    fi
  fi
fi

run osascript -e 'tell application "Ollama" to quit' || true
[ "$MODE" = "--dry" ] || sleep 2
run open -a Ollama
[ "$MODE" = "--dry" ] || { echo "Done. Check with:  ollama ps   (after your next request)"; }
