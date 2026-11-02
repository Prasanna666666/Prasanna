"""Starting the UI: browser server, native window and the macOS .app bundle."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from .config import Paths
from .safety import enable_offline_guard

DEFAULT_PORT = 8765


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

        webview.create_window("Aperture", url, width=1440, height=900, min_size=(900, 600))
        webview.start()
    except Exception:
        subprocess.run(["open", url], check=False)  # noqa: S603, S607
        return 0
    if started is not None:  # we started the server, so closing the window stops it
        started.terminate()
    return 0


def install_app_bundle(paths: Paths, destination: Path | None = None) -> Path:
    """Create ``Aperture.app``: a double-clickable launcher (no terminal needed).

    The bundle holds only a tiny shell script; the Python environment, data and
    models stay on the external drive."""
    destination = destination or Path.home() / "Applications" / "Aperture.app"
    macos = destination / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    script = f"""#!/bin/bash
export APERTURE_DRIVE="{paths.drive}"
if [ ! -d "{paths.drive}" ]; then
  /usr/bin/osascript -e 'display alert "Aperture" message "The external drive {paths.drive} is not connected."'
  exit 1
fi
exec "{sys.executable}" -m aperture app >> "{paths.logs}/app.log" 2>&1
"""
    executable = macos / "Aperture"
    executable.write_text(script)
    executable.chmod(0o755)
    info = {
        "CFBundleName": "Aperture",
        "CFBundleDisplayName": "Aperture",
        "CFBundleIdentifier": "local.aperture.app",
        "CFBundleVersion": "1.0",
        "CFBundleExecutable": "Aperture",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "12.0",
    }
    (destination / "Contents" / "Info.plist").write_bytes(plistlib.dumps(info))
    os.utime(destination)
    return destination
