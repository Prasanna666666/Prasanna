#!/bin/bash
# Stop Atlas starting at login. Your data and the running containers are not touched.
launchctl bootout "gui/$(id -u)/local.atlas.start" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/local.atlas.start.plist"
rm -rf "$HOME/Applications/Atlas.app"
echo "Atlas no longer starts at login."
