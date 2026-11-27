#!/usr/bin/env bash
# Build Atlas.app: the Swift app plus a private Python environment with the Core inside it. Built and smoke-tested by the CI `app` job on a macOS runner (the app launches, starts its Core and stops it on quit).
# The bundled environment is a venv: it still uses the Python 3.11+ it was made from (a standalone, relocatable Python is not bundled yet), and needs SQLCipher (`brew install sqlcipher`).
# Not done here: Developer ID signing with the hardened runtime, notarisation, the update channel, the model manifest/key installation (G-O12).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:-$here/build/Atlas.app}"
(cd "$here/app" && swift build -c release)
rm -rf "$out"
mkdir -p "$out/Contents/MacOS" "$out/Contents/Resources"
cp "$here/app/.build/release/AtlasApp" "$out/Contents/MacOS/Atlas"
# SwiftPM resources (the UX catalogue) live in a bundle next to the executable; `Bundle.module` finds it in Contents/Resources of the app. Without it the app traps on its first lookup.
for resources in "$here"/app/.build/release/*.bundle; do cp -R "$resources" "$out/Contents/Resources/"; done
# SwiftPM names the bundle <package>_<target>.bundle; the package is "Atlas", so this is Atlas_AtlasKit.bundle
compgen -G "$out/Contents/Resources/*_AtlasKit.bundle" >/dev/null || { echo "the AtlasKit resource bundle is missing from the app" >&2; exit 1; }
python3 -m venv "$out/Contents/Resources/python"
py="$out/Contents/Resources/python/bin"
if [ "$(uname -s)" = "Darwin" ]; then  # sqlcipher3-binary has no macOS wheel: build the binding against Homebrew's SQLCipher
  prefix="$(brew --prefix sqlcipher)"
  CFLAGS="-I$prefix/include -I$prefix/include/sqlcipher" LDFLAGS="-L$prefix/lib" "$py/pip" install --quiet sqlcipher3
  "$py/pip" install --quiet "$here/kit" "$here/core[macos,browser]"  # [macos]: the Calendar, Contacts and Photos frameworks; [browser]: the isolated browser
else
  "$py/pip" install --quiet "$here/kit[secure]" "$here/core"
fi
if [ "${ATLAS_BUNDLE_BROWSER:-0}" = "1" ]; then  # the browser travels inside the app so nothing is downloaded when the owner uses it
  PLAYWRIGHT_BROWSERS_PATH="$out/Contents/Resources/browsers" "$py/python" -m playwright install chromium
fi
cat > "$out/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Atlas</string>
  <key>CFBundleIdentifier</key><string>invalid.atlas.app</string>
  <key>CFBundleExecutable</key><string>Atlas</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>NSCalendarsFullAccessUsageDescription</key><string>Atlas reads your calendar on this Mac, only while you have it turned on, so it can answer questions about your events. It never leaves your Mac.</string>
  <key>NSContactsUsageDescription</key><string>Atlas reads your contacts on this Mac, only while you have them turned on, so it can answer questions about people. It never leaves your Mac.</string>
  <key>NSPhotoLibraryUsageDescription</key><string>Atlas reads the dates and kinds of your photos on this Mac, never the pictures themselves, only while you have them turned on.</string>
  <key>NSMicrophoneUsageDescription</key><string>Atlas listens only while you press the microphone button, so you can dictate a question. Speech is turned into text on this Mac and never leaves it.</string>
  <key>NSSpeechRecognitionUsageDescription</key><string>Atlas turns your speech into text on this Mac, never on a server, only while you dictate.</string>
  <key>NSAppleEventsUsageDescription</key><string>Atlas reads your Notes on this Mac, only while you have them turned on, so it can answer questions about them. They never leave your Mac.</string>
</dict></plist>
PLIST
codesign --force --deep --sign - "$out"  # ad-hoc only: NOT a release signature
echo "built $out (ad-hoc signed, not notarised)"
