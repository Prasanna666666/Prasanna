#!/bin/bash
# Apple's text recognition for scanned pages, on the Mac's own chip: ./scripts/apple-ocr.sh start | stop.
# The helper runs in a macOS sandbox with no network and may write only into a RAM disk, so the pictures of your pages are never on a disk. If anything here fails, Atlas reads
# scanned pages with the usual reader (Tesseract) and says so: nothing depends on this.
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.atlas/atlas-ocr"
PIDFILE="$HOME/.atlas/atlas-ocr.pid"
MOUNT=/Volumes/AtlasOCR
stop() {
  [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null; rm -f "$PIDFILE"
  [ -d "$MOUNT" ] && hdiutil detach "$MOUNT" -force >/dev/null 2>&1
  return 0
}
case "${1:-}" in
  stop) stop ;;
  start)
    [ "$(uname)" = Darwin ] || exit 1
    command -v swiftc >/dev/null || { echo "Apple text recognition: not available (the Xcode command line tools are not installed)."; exit 1; }
    mkdir -p "$HOME/.atlas"
    if [ ! -x "$BIN" ] || [ "$HERE/atlas-ocr.swift" -nt "$BIN" ]; then
      swiftc -O "$HERE/atlas-ocr.swift" -o "$BIN" 2>"$HOME/.atlas/atlas-ocr.build.log" || { echo "Apple text recognition: could not be built (see ~/.atlas/atlas-ocr.build.log)."; exit 1; }
    fi
    stop
    DEV="$(hdiutil attach -nomount ram://524288 2>/dev/null | awk '{print $1}')"   # 256 MB, in memory only
    [ -n "$DEV" ] && diskutil erasevolume HFS+ AtlasOCR "$DEV" >/dev/null 2>&1 || { echo "Apple text recognition: could not make its memory disk."; exit 1; }
    nohup sandbox-exec -D "DIR=$MOUNT" -f "$HERE/atlas-ocr.sb" "$BIN" "$MOUNT" >"$HOME/.atlas/atlas-ocr.log" 2>&1 &
    echo $! >"$PIDFILE"
    sleep 2
    kill -0 "$(cat "$PIDFILE")" 2>/dev/null && [ -f "$MOUNT/alive" ] || { echo "Apple text recognition: did not start (see ~/.atlas/atlas-ocr.log)."; stop; exit 1; }
    echo "Apple text recognition is running (on the Mac's chip, sandboxed, no network, pictures only in memory)."
    ;;
  *) echo "usage: apple-ocr.sh start|stop"; exit 2 ;;
esac
