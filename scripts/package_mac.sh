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
python3 -m venv "$out/Contents/Resources/python"
py="$out/Contents/Resources/python/bin"
if [ "$(uname -s)" = "Darwin" ]; then  # sqlcipher3-binary has no macOS wheel: build the binding against Homebrew's SQLCipher
  prefix="$(brew --prefix sqlcipher)"
  CFLAGS="-I$prefix/include -I$prefix/include/sqlcipher" LDFLAGS="-L$prefix/lib" "$py/pip" install --quiet sqlcipher3
  "$py/pip" install --quiet "$here/kit" "$here/core"
else
  "$py/pip" install --quiet "$here/kit[secure]" "$here/core"
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
</dict></plist>
PLIST
codesign --force --deep --sign - "$out"  # ad-hoc only: NOT a release signature
echo "built $out (ad-hoc signed, not notarised)"
