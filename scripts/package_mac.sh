#!/usr/bin/env bash
# Build Atlas.app: the Swift app plus a private Python with the Core inside it. UNVERIFIED: never run (needs a Mac with Xcode command line tools and Python 3.11+).
# Not done here: Developer ID signing with the hardened runtime, notarisation, the update channel, the model manifest/key installation (G-O12).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${1:-$here/build/Atlas.app}"
(cd "$here/app" && swift build -c release)
rm -rf "$out"
mkdir -p "$out/Contents/MacOS" "$out/Contents/Resources"
cp "$here/app/.build/release/AtlasApp" "$out/Contents/MacOS/Atlas"
python3 -m venv "$out/Contents/Resources/python"
"$out/Contents/Resources/python/bin/pip" install --quiet "$here/kit[secure]" "$here/core"
cat > "$out/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Atlas</string>
  <key>CFBundleIdentifier</key><string>invalid.atlas.app</string>
  <key>CFBundleExecutable</key><string>Atlas</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
</dict></plist>
PLIST
codesign --force --deep --sign - "$out"  # ad-hoc only: NOT a release signature
echo "built $out (ad-hoc signed, not notarised)"
