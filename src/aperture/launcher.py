"""Starting the UI: browser server, native window and the macOS .app bundle."""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .config import Paths
from .safety import enable_offline_guard

DEFAULT_PORT = 8765
APP_NAME = "Lumo"


def ui_script() -> Path:
    from . import ui

    return Path(ui.__file__).resolve().parent / "app.py"


def run_ui(port: int = DEFAULT_PORT) -> int:
    """Serve the Streamlit UI on loopback only, behind the offline guard."""
    enable_offline_guard()
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit", "run", str(ui_script()),
        "--server.address", "127.0.0.1", "--server.port", str(port),
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
        "--server.fileWatcherType", "none", "--client.toolbarMode", "minimal",
    ]  # fmt: skip
    return int(stcli.main() or 0)


def _healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/_stcore/health", timeout=1) as r:
            return r.status == 200
    except OSError:
        return False


def run_window(port: int = DEFAULT_PORT) -> int:
    """Open Aperture in a native window (falls back to the default browser)."""
    started: subprocess.Popen[bytes] | None = None
    if not _healthy(port):
        started = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "aperture", "ui", "--port", str(port)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
        )  # fmt: skip
        for _ in range(120):
            if _healthy(port):
                break
            time.sleep(0.5)
    url = f"http://127.0.0.1:{port}"
    try:
        import webview

        webview.create_window(APP_NAME, url, width=1440, height=900, min_size=(900, 600))
        webview.start()
    except Exception:
        subprocess.run(["open", url], check=False)  # noqa: S603, S607
        return 0
    if started is not None:  # we started the server, so closing the window stops it
        started.terminate()
    return 0


def install_app_bundle(paths: Paths, destination: Path | None = None) -> Path:
    """Create ``Lumo.app``: a double-clickable launcher (no terminal needed).

    The bundle holds only a tiny shell script; the Python environment, data and
    models stay on the external drive."""
    destination = destination or Path.home() / "Applications" / f"{APP_NAME}.app"
    macos = destination / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[2]
    update = ""
    if (repo / ".git").is_dir():  # source checkout: pick up fixes on launch when online (best effort, optional)
        update = (
            'if [ -z "$APERTURE_NO_UPDATE" ]; then\n'
            "  (export GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/true;\n"
            f'   /usr/bin/git -C "{repo}" pull --ff-only -q >/dev/null 2>&1 &)\n'
            "fi\n"
        )
    port = DEFAULT_PORT
    script = f"""#!/bin/bash
export APERTURE_DRIVE="{paths.drive}"
LOG="{paths.logs}/app.log"
if [ ! -d "{paths.drive}" ]; then
  /usr/bin/osascript -e 'display alert "{APP_NAME}" message "The external drive {paths.drive} is not connected."'
  exit 1
fi
exec >> "$LOG" 2>&1
echo "--- $(date) launching {APP_NAME}"
URL="http://127.0.0.1:{port}"
healthy() {{ /usr/bin/curl -sf -m 1 "$URL/_stcore/health" >/dev/null; }}
show() {{
  for app in "Google Chrome" "Microsoft Edge" "Brave Browser" "Chromium"; do
    if [ -d "/Applications/$app.app" ]; then
      /usr/bin/open -na "$app" --args --app="$URL" --window-size=1440,900 \
        --user-data-dir="$HOME/Library/Application Support/{APP_NAME}/window"
      return
    fi
  done
  /usr/bin/open "$URL"
}}
if healthy; then show; exit 0; fi
/usr/bin/osascript -e 'display notification "Starting {APP_NAME}. This can take up to a minute." with title "{APP_NAME}"' >/dev/null 2>&1 &
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/Ollama.app/Contents/Resources:$PATH"
if ! /usr/bin/curl -sf -m 1 http://127.0.0.1:11434 >/dev/null; then
  /usr/bin/open -ga Ollama 2>/dev/null || (nohup ollama serve >/dev/null 2>&1 &)
fi
{update}nohup "{sys.executable}" -m aperture ui --port {port} >> "$LOG" 2>&1 &
for _ in $(seq 1 180); do
  if healthy; then show; exit 0; fi
  sleep 1
done
/usr/bin/osascript -e 'display alert "{APP_NAME}" message "It did not start. See {paths.logs}/app.log"'
exit 1
"""
    executable = macos / APP_NAME
    executable.write_text(script)
    executable.chmod(0o755)
    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleIdentifier": "local.aperture.app",
        "CFBundleVersion": "1.0",
        "CFBundleExecutable": APP_NAME,
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "12.0",
    }
    from .icon import write_icns

    resources = destination / "Contents" / "Resources"
    if write_icns(resources / "AppIcon.icns"):
        info["CFBundleIconFile"] = "AppIcon"
    old = destination.parent / "Aperture.app"  # earlier name: remove the stale launcher
    if old.is_dir() and old != destination:
        shutil.rmtree(old, ignore_errors=True)
    (destination / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    os.utime(destination)
    _sign(destination)
    return destination


def _sign(bundle: Path) -> None:
    """Ad-hoc sign the bundle and clear the download flag so macOS lets a click start it."""
    for cmd in (
        ["/usr/bin/xattr", "-cr", str(bundle)],
        ["/usr/bin/codesign", "--force", "--deep", "--sign", "-", str(bundle)],
        ["/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister", "-f", str(bundle)],
    ):  # fmt: skip
        if Path(cmd[0]).exists():
            subprocess.run(cmd, check=False, capture_output=True)  # noqa: S603
