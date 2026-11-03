"""Photo commands must run in the sandbox or Docker; the normal launcher is `aperture secure-ui`."""

from pathlib import Path

import pytest

from aperture import cli

ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("APERTURE_SANDBOXED", raising=False)


@pytest.mark.parametrize("cmd", ["ui", "app", "scan", "ask hi", "caption", "install-service", "install-launcher"])
def test_photo_commands_refuse_outside_the_secure_environment(cmd, capsys):
    assert cli.main(cmd.split()) == 2
    out = capsys.readouterr().out
    assert "Refusing to run outside the secure environment" in out and "aperture secure-ui" in out and "--insecure" in out


def test_non_photo_commands_are_not_blocked():
    ns = cli.build_parser().parse_args(["doctor"])
    assert ns.command not in cli.GUARDED
    for cmd in ("doctor", "settings", "stats", "eval-plans", "eval", "bench", "fetch-models"):
        assert cmd not in cli.GUARDED


def test_override_and_secure_marker_let_it_through(monkeypatch):
    seen = []
    monkeypatch.setattr("aperture.launcher.run_ui", lambda port: seen.append(port) or 0)
    monkeypatch.setattr(cli, "configure_environment", lambda *a, **k: None)
    monkeypatch.setattr(cli, "enable_offline_guard", lambda: None)
    assert cli.main(["--insecure", "ui", "--port", "9001"]) == 0
    monkeypatch.setenv("APERTURE_SANDBOXED", "1")
    assert cli.main(["ui", "--port", "9002"]) == 0
    assert seen == [9001, 9002]


def test_secure_ui_builds_the_sandbox_command(monkeypatch, tmp_path):
    photos, exports = tmp_path / "Photos", tmp_path / "Exports"
    photos.mkdir(), exports.mkdir()
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.setattr(cli, "_require_drive", lambda paths: 0)
    monkeypatch.setattr(cli.Settings, "load", classmethod(lambda cls, p: cls(photo_dir=str(photos), export_dir=str(exports))))
    calls = []
    import subprocess
    monkeypatch.setattr(subprocess, "call", lambda cmd, env=None: calls.append((cmd, env)) or 0)
    assert cli.main(["secure-ui", "--port", "9100", "--no-browser"]) == 0
    cmd, env = calls[0]
    assert cmd[0].endswith("scripts/aperture-sandboxed.sh") and cmd[1] == str(photos) and cmd[2] == str(exports)
    assert cmd[3:] == ["--", cli.sys.executable, "-m", "aperture", "ui", "--port", "9100"]
    assert env["ALLOW_MOVES"] == "no"
    cli.main(["secure-ui", "--allow-moves", "--no-browser"])
    assert calls[1][1]["ALLOW_MOVES"] == "yes"


def test_secure_ui_explains_a_missing_photo_folder_or_wrong_os(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.sys, "platform", "linux")
    assert cli.main(["secure-ui"]) == 2 and "needs macOS" in capsys.readouterr().out
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.setattr(cli, "_require_drive", lambda paths: 0)
    monkeypatch.setattr(cli.Settings, "load", classmethod(lambda cls, p: cls(photo_dir=str(tmp_path / "nope"))))
    assert cli.main(["secure-ui"]) == 2
    out = capsys.readouterr().out
    assert "Photo folder not found" in out and "aperture settings --photo-dir" in out


def test_sandbox_script_and_docker_mark_the_environment_secure():
    assert "APERTURE_SANDBOXED=1" in (ROOT / "scripts" / "aperture-sandboxed.sh").read_text()
    assert "APERTURE_SANDBOXED=1" in (ROOT / "Dockerfile.aperture").read_text()


def test_profile_keeps_aperture_folder_writable_inside_a_read_only_photo_folder():
    text = (ROOT / "scripts" / "aperture-sandbox.sb").read_text()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(";;")]
    deny = next(i for i, ln in enumerate(lines) if "deny file-write*" in ln)
    allow_root = next(i for i, ln in enumerate(lines) if 'allow file-write* (subpath (param "AP_ROOT"))' in ln)
    assert allow_root > deny, "later rules win: the re-allow must come after the deny"
    assert "AP_ROOT" in (ROOT / "scripts" / "aperture-sandboxed.sh").read_text()


def test_secure_ui_passes_the_aperture_folder(monkeypatch, tmp_path):
    photos = tmp_path / "Photos"
    photos.mkdir()
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.setattr(cli, "_require_drive", lambda paths: 0)
    monkeypatch.setattr(cli.Settings, "load", classmethod(lambda cls, p: cls(photo_dir=str(photos))))
    seen = []
    import subprocess
    monkeypatch.setattr(subprocess, "call", lambda cmd, env=None: seen.append(env) or 0)
    cli.main(["secure-ui", "--no-browser"])
    assert seen[0]["AP_ROOT"].endswith("Aperture")


def test_drive_check_in_sandbox_needs_only_the_aperture_folder_writable(monkeypatch, tmp_path):
    from aperture import safety

    drive = tmp_path / "Expansion"
    (drive / "Aperture").mkdir(parents=True)
    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    real_access = safety.os.access
    monkeypatch.setattr(safety.os, "access", lambda p, m: False if Path(p) == drive else real_access(p, m))
    monkeypatch.delenv("APERTURE_SANDBOXED", raising=False)
    assert "read-only" in (safety.drive_problem(drive) or "")  # outside the sandbox: still refused
    monkeypatch.setenv("APERTURE_SANDBOXED", "1")
    assert safety.drive_problem(drive) is None  # sandbox: Aperture's own folder is writable, that is enough
    monkeypatch.setattr(safety.os, "access", lambda p, m: False)
    assert "read-only" in (safety.drive_problem(drive) or "")  # its own folder unwritable too: refused


def _secure_setup(monkeypatch, tmp_path):
    photos = tmp_path / "Photos"
    photos.mkdir(exist_ok=True)
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    monkeypatch.setattr(cli, "_require_drive", lambda paths: 0)
    monkeypatch.setattr(cli.Settings, "load", classmethod(lambda cls, p: cls(photo_dir=str(photos))))
    calls = []
    import subprocess
    monkeypatch.setattr(subprocess, "call", lambda cmd, env=None: calls.append(cmd) or 0)
    return calls


def test_secure_ui_picks_a_free_port_by_itself(monkeypatch, tmp_path, capsys):
    import socket

    calls = _secure_setup(monkeypatch, tmp_path)
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    busy = blocker.getsockname()[1]
    monkeypatch.setattr(cli, "first_free_port", lambda start=8765, tries=25: next(
        p for p in range(busy, busy + 25) if cli.port_is_free(p)))
    try:
        assert cli.main(["secure-ui", "--no-browser"]) == 0
    finally:
        blocker.close()
    assert calls[0][-1] == str(busy + 1) and "is busy" in capsys.readouterr().out


def test_explicit_busy_port_is_refused_with_a_clear_message(monkeypatch, tmp_path, capsys):
    import socket

    calls = _secure_setup(monkeypatch, tmp_path)
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    try:
        assert cli.main(["secure-ui", "--port", str(blocker.getsockname()[1]), "--no-browser"]) == 2
    finally:
        blocker.close()
    assert not calls and "Leave out --port" in capsys.readouterr().out


def test_browser_opens_once_the_server_answers(monkeypatch):
    import urllib.request
    import webbrowser

    opened = []
    attempts = iter([OSError("not yet"), OSError("not yet"), None])

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=1):
        outcome = next(attempts)
        if outcome is not None:
            raise outcome
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)
    cli.open_when_ready(8770)
    assert opened == ["http://127.0.0.1:8770"]
