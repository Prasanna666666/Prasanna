#!/usr/bin/env bash
# Developer ID signing and notarisation of Atlas.app (Stage 7). Needs an Apple Developer ID account: it cannot run without one.
#
#   DEVELOPER_ID="Developer ID Application: Name (TEAMID)"  NOTARY_PROFILE=atlas-notary  scripts/sign_and_notarize.sh Atlas.app [--dry-run]
#
# NOTARY_PROFILE is a keychain profile made once with `xcrun notarytool store-credentials`; no password or key is ever passed on the command line, in the environment, or printed.
# --dry-run prints the exact commands in order without running them (used by the test, and to review them before a real run).
set -euo pipefail

app="${1:-}"
dry=0
[ "${2:-}" = "--dry-run" ] && dry=1

[ -n "$app" ] || { echo "usage: sign_and_notarize.sh Atlas.app [--dry-run]" >&2; exit 64; }
[ -n "${DEVELOPER_ID:-}" ] || { echo "DEVELOPER_ID is not set: an Apple Developer ID certificate is needed to sign" >&2; exit 2; }
[ -n "${NOTARY_PROFILE:-}" ] || { echo "NOTARY_PROFILE is not set: store notarytool credentials in the keychain first" >&2; exit 2; }
case "$DEVELOPER_ID" in "Developer ID Application:"*) ;; *) echo "DEVELOPER_ID must be a 'Developer ID Application' identity" >&2; exit 2;; esac

run() {
  if [ "$dry" = 1 ]; then printf '%s\n' "$*"; else "$@"; fi
}

zip="${app%.app}-notarize.zip"
# 1. sign every nested executable first (inside out), then the app, with the hardened runtime and a secure timestamp
run find "$app/Contents" -type f \( -perm -u+x -o -name '*.dylib' -o -name '*.so' \) -exec codesign --force --options runtime --timestamp --sign "$DEVELOPER_ID" {} +
run codesign --force --options runtime --timestamp --sign "$DEVELOPER_ID" "$app"
run codesign --verify --deep --strict --verbose=2 "$app"
# 2. notarise and wait for the verdict
run ditto -c -k --keepParent "$app" "$zip"
run xcrun notarytool submit "$zip" --keychain-profile "$NOTARY_PROFILE" --wait
# 3. staple the ticket so the app opens offline, then let Gatekeeper judge it
run xcrun stapler staple "$app"
run spctl --assess --type execute --verbose=2 "$app"
