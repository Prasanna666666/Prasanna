#!/bin/bash
# Run the idle check every 15 minutes, at the lowest priority (a launch agent of your own user; nothing else is installed). Safe to run again.
set -euo pipefail
[ "$(uname)" = "Darwin" ] || exit 0
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/local.atlas.auto-read.plist"
mkdir -p "$(dirname "$PLIST")"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.atlas.auto-read</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$HERE/scripts/auto-read.sh</string></array>
  <key>StartInterval</key><integer>900</integer>
  <key>Nice</key><integer>15</integer>
  <key>LowPriorityIO</key><true/>
  <key>ProcessType</key><string>Background</string>
</dict></plist>
PL
launchctl unload "$PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST" >/dev/null 2>&1 || true
