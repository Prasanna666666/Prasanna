#!/bin/bash
# The idle check: when this Mac has been idle for a while and is plugged in, ask Atlas to read what is new. Atlas reads by itself only when fewer than 50 files
# are waiting and never before you have pressed Read new files once; a big read is always your own decision. Costs almost nothing when it does not run:
# a few cheap checks. Turn it off with:  touch ~/.atlas-auto-off   (on again: rm ~/.atlas-auto-off)
set -u
[ -e "$HOME/.atlas-auto-off" ] && exit 0
IDLE_SECONDS="${ATLAS_AUTO_IDLE:-300}"
idle=$(ioreg -c IOHIDSystem 2>/dev/null | awk '/HIDIdleTime/ {print int($NF/1000000000); exit}')
[ "${idle:-0}" -ge "$IDLE_SECONDS" ] || exit 0                       # someone is using the Mac
pmset -g batt 2>/dev/null | head -1 | grep -q "AC Power" || exit 0   # only on power
curl -s -m 2 -o /dev/null "http://127.0.0.1:11434/api/tags" || exit 0 # the model is not running: nothing to do
curl -s -m 20 -o /dev/null -X POST --resolve atlas.localhost:8000:127.0.0.1 \
  -H "Origin: http://atlas.localhost:8000" -H "X-Atlas: 1" "http://atlas.localhost:8000/_atlas/api/auto" || true
