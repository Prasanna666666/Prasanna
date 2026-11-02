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

from .config import Paths, default_paths
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


def _run(cmd: list[str]) -> str:
    """Run a macOS helper; a missing or failing tool just yields no output."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False).stdout  # noqa: S603
    except OSError:
        return ""


def _run_ok(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, check=False).returncode == 0  # noqa: S603
    except OSError:
        return False


def _open_browser(url: str) -> None:
    """Show the page in a browser window and bring it to the front; every attempt is logged."""
    candidates = [
        app
        for app in ("Google Chrome", "Safari", "Microsoft Edge", "Brave Browser", "Firefox")
        if Path(f"/Applications/{app}.app").is_dir()
        or Path(f"/System/Volumes/Preboot/Cryptexes/App/System/Applications/{app}.app").is_dir()
    ]
    for app in candidates[:1]:
        ok = _run_ok(["/usr/bin/open", "-a", app, url])
        print(f"open -a {app!r}: {'ok' if ok else 'failed'}", flush=True)
        _run(["/usr/bin/osascript", "-e", f'tell application "{app}" to activate'])
        if ok:
            return
    ok = _run_ok(["/usr/bin/open", url])
    print(f"open default browser: {'ok' if ok else 'failed'}", flush=True)


def _notify(text: str, *, alert: bool = False) -> None:
    script = f'display alert "{APP_NAME}" message "{text}"' if alert else f'display notification "{text}" with title "{APP_NAME}"'
    try:
        subprocess.Popen(["/usr/bin/osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # noqa: S603
    except OSError:
        pass


def _free_port(port: int) -> None:
    """Remove anything stuck from an earlier run (hung or suspended servers) before starting clean."""
    pids = set(_run(["/usr/sbin/lsof", "-ti", f"tcp:{port}"]).split())
    pids |= set(_run(["/usr/bin/pgrep", "-f", "aperture ui"]).split())
    for pid in pids - {str(os.getpid())}:
        _run(["/bin/kill", "-9", pid])


def _start_ollama() -> None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434", timeout=1):
            return
    except OSError:
        pass
    if _run_ok(["/usr/bin/open", "-ga", "Ollama"]):
        return
    env = {**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")}
    try:
        cmd = ["/usr/bin/env", "ollama", "serve"]
        subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)  # noqa: S603
    except OSError:
        pass


def _update_in_background() -> None:
    """Best-effort ``git pull`` of the source checkout; never waited for, never prompts."""
    repo = Path(__file__).resolve().parents[2]
    if os.environ.get("APERTURE_NO_UPDATE") or not (repo / ".git").is_dir():
        return
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/usr/bin/true"}
    subprocess.Popen(  # noqa: S603
        ["/usr/bin/git", "-C", str(repo), "pull", "--ff-only", "-q"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
    )  # fmt: skip


def run_window(port: int = DEFAULT_PORT) -> int:
    """What a click on the Lumo icon does: start cleanly if needed, then open the app."""
    paths = default_paths()
    url = f"http://127.0.0.1:{port}"
    print(f"--- {time.strftime('%c')} launching {APP_NAME}", flush=True)
    if not paths.drive.is_dir():
        _notify(f"The external drive {paths.drive} is not connected.", alert=True)
        return 1
    if _healthy(port):
        _open_browser(url)
        return 0
    _notify(f"Starting {APP_NAME}. This can take up to a minute.")
    _free_port(port)
    _start_ollama()
    _update_in_background()
    paths.logs.mkdir(parents=True, exist_ok=True)
    with open(paths.logs / "app.log", "a") as log:
        server = subprocess.Popen(  # noqa: S603
            [sys.executable, "-m", "aperture", "ui", "--port", str(port)],
            stdout=log, stderr=log, start_new_session=True,
        )  # fmt: skip
    for _ in range(360):
        if _healthy(port):
            _open_browser(url)
            return 0
        if server.poll() is not None:
            break
        time.sleep(0.5)
    _notify(f"It did not start. Details: {paths.logs}/app.log", alert=True)
    return 1


def install_app_bundle(paths: Paths, destination: Path | None = None) -> Path:
    """Create ``Lumo.app``: a double-clickable launcher (no terminal needed).

    The bundle holds only a tiny shell script; the Python environment, data and
    models stay on the external drive."""
    destination = destination or Path.home() / "Applications" / f"{APP_NAME}.app"
    macos = destination / "Contents" / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)
    script = f"""#!/bin/bash
export APERTURE_DRIVE="{paths.drive}"
mkdir -p "{paths.logs}" 2>/dev/null
nohup "{sys.executable}" -m aperture app >> "{paths.logs}/app.log" 2>&1 &
disown
exit 0
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


SERVICE_LABEL = "local.lumo.server"


def install_service(paths: Paths, port: int = DEFAULT_PORT) -> str:
    """Keep the web UI running in the background from login onwards (a macOS LaunchAgent).

    Also removes the old double-click app bundles.  Returns the address to bookmark."""
    repo = Path(__file__).resolve().parents[2]
    pull = f'/usr/bin/git -C "{repo}" pull --ff-only -q >/dev/null 2>&1 &' if (repo / ".git").is_dir() else ""
    command = (
        f'export APERTURE_DRIVE="{paths.drive}" GIT_TERMINAL_PROMPT=0 GIT_ASKPASS=/usr/bin/true; '
        f'export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"; '
        f'if [ ! -d "{paths.drive}" ]; then exit 1; fi; '
        f"/usr/bin/curl -sf -m 1 http://127.0.0.1:11434 >/dev/null || /usr/bin/open -ga Ollama; "
        f"{pull} "
        f'exec "{sys.executable}" -m aperture ui --port {port}'
    )
    agents = Path.home() / "Library" / "LaunchAgents"
    agents.mkdir(parents=True, exist_ok=True)
    plist = agents / f"{SERVICE_LABEL}.plist"
    log = str(paths.logs / "server.log")
    plist.write_bytes(
        plistlib.dumps(
            {
                "Label": SERVICE_LABEL,
                "ProgramArguments": ["/bin/bash", "-c", command],
                "RunAtLoad": True,
                "KeepAlive": True,
                "ThrottleInterval": 20,  # retried every 20 s, e.g. until the drive is plugged in
                "StandardOutPath": log,
                "StandardErrorPath": log,
            }
        )
    )
    paths.logs.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    _run(["/bin/launchctl", "bootout", f"{domain}/{SERVICE_LABEL}"])  # replace an older copy
    _free_port(port)  # clear leftovers from earlier manual starts
    _run(["/bin/launchctl", "bootstrap", domain, str(plist)])
    _run(["/bin/launchctl", "kickstart", "-k", f"{domain}/{SERVICE_LABEL}"])
    for old in (f"{APP_NAME}.app", "Aperture.app"):
        shutil.rmtree(Path.home() / "Applications" / old, ignore_errors=True)
    return f"http://{APP_NAME.lower()}.localhost:{port}"
