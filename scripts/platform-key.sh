#!/bin/bash
# Source this from an up.sh. Gives PLATFORM_KEY: the secret the platform's own programs sign their calls to each other with, so no other program on
# this Mac can use a service's port. It lives in the macOS Keychain (created on first use), never in a file or in git.
SERVICE=atlas-platform-key
if [ "$(uname)" = "Darwin" ]; then
  if ! PLATFORM_KEY="$(security find-generic-password -a "$USER" -s "$SERVICE" -w 2>/dev/null)"; then
    PLATFORM_KEY="$(openssl rand -base64 32)"
    security add-generic-password -a "$USER" -s "$SERVICE" -w "$PLATFORM_KEY" -T /usr/bin/security -U
    echo "Created the platform key in your Keychain ('$SERVICE')."
  fi
fi
export PLATFORM_KEY="${PLATFORM_KEY:-}"
