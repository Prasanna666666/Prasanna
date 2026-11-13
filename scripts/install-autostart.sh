#!/bin/bash
# Make Atlas start by itself every time you log in, and put an "Atlas" app in ~/Applications that opens it. Run once:  ./scripts/install-autostart.sh
#   ATLAS_NO_MAIL=1 ./scripts/install-autostart.sh      (without Apple Mail)
# Undo: ./scripts/uninstall-autostart.sh
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
[ "$(uname)" = "Darwin" ] || { echo "This is for the Mac."; exit 2; }
PLIST="$HOME/Library/LaunchAgents/local.atlas.start.plist"
LOG="$HOME/Library/Logs/atlas-start.log"
mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs" "$HOME/Applications"
chmod +x scripts/start-at-login.sh
cat > "$PLIST" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>local.atlas.start</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$ROOT/scripts/start-at-login.sh</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:/Applications/Docker.app/Contents/Resources/bin</string>
    <key>ATLAS_NO_MAIL</key><string>${ATLAS_NO_MAIL:-}</string>
    <key>LIBRARY_INBOX_MODE</key><string>${LIBRARY_INBOX_MODE:-ro}</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>Nice</key><integer>10</integer>
  <key>LowPriorityIO</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
PLISTEOF
launchctl bootout "gui/$(id -u)/local.atlas.start" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
# the apps: "Atlas" opens it, "Stop Atlas" stops everything (put them in the Dock)
scripts/make-apps.sh
echo "Done. Atlas now starts when you log in (log: $LOG)."
echo "Open it with the Atlas app in ~/Applications (drag it to the Dock), or go to http://atlas.localhost:8000"
echo "Also tick 'Start Docker Desktop when you sign in' in Docker's settings (General) so it comes up even before this runs."
