#!/bin/bash
# Run Aperture inside a macOS sandbox: no internet, originals read-only (kernel-enforced).
#
#   scripts/aperture-sandboxed.sh PHOTO_DIR [EXPORT_DIR] -- aperture ui
#   scripts/aperture-sandboxed.sh --selftest PHOTO_DIR      # prove the sandbox works on this Mac
#   ALLOW_MOVES=yes ...                                     # only if you enabled photo moves in Settings
#
# Network is locked off twice: by the OS sandbox and by APERTURE_NEVER_ONLINE=1. `aperture fetch-models` is refused here;
# run it once with the normal install before using the sandbox.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PROFILE="$HERE/aperture-sandbox.sb"

[ "$(uname)" = "Darwin" ] || { echo "This needs macOS (sandbox-exec)."; exit 2; }

SELFTEST=0
if [ "${1:-}" = "--selftest" ]; then SELFTEST=1; shift; fi
[ $# -ge 1 ] || { sed -n '2,8p' "$0"; exit 2; }
PHOTO_DIR="$(cd "$1" && pwd -P)"; shift
EXPORT_DIR="/nonexistent-export-dir"
if [ $# -ge 1 ] && [ "$1" != "--" ]; then EXPORT_DIR="$(cd "$1" && pwd -P)"; shift; fi
[ "${1:-}" = "--" ] && shift

export APERTURE_NEVER_ONLINE=1
SB=(sandbox-exec -f "$PROFILE" -D "PHOTO_DIR=$PHOTO_DIR" -D "EXPORT_DIR=$EXPORT_DIR" -D "ALLOW_MOVES=${ALLOW_MOVES:-no}")

if [ "$SELFTEST" = 1 ]; then
  exec "${SB[@]}" python3 - "$PHOTO_DIR" <<'PY'
import os, socket, sys, threading

def tcp(host, port):
    s = socket.socket(); s.settimeout(3)
    try:
        s.connect((host, port)); return True
    except OSError:
        return False
    finally:
        s.close()

srv = socket.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(1)
threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True).start()
results = {
    "internet blocked (1.1.1.1:443)": not tcp("1.1.1.1", 443),
    "loopback works": tcp("127.0.0.1", srv.getsockname()[1]),
}
try:
    open(os.path.join(sys.argv[1], ".aperture-sandbox-test"), "w").close()
    os.remove(os.path.join(sys.argv[1], ".aperture-sandbox-test"))
    results["photo folder read-only"] = False
except OSError:
    results["photo folder read-only"] = True
for name, ok in results.items():
    print(("PASS  " if ok else "FAIL  ") + name)
sys.exit(0 if all(results.values()) else 1)
PY
fi

[ $# -ge 1 ] || { echo "Give a command after --, e.g. -- aperture ui"; exit 2; }
exec "${SB[@]}" "$@"
