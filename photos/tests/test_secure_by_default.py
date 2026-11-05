"""Photo commands must run in the sandbox or Docker; the normal launcher is `aperture secure-ui`."""

from pathlib import Path

import pytest

from aperture import cli

ROOT = Path(__file__).parent.parent


class FakePopen:
    pid = 424242

    def __init__(self, record):
        record()

    def wait(self):
        return 0


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    monkeypatch.delenv("APERTURE_SANDBOXED", raising=False)
    monkeypatch.setenv("APERTURE_DRIVE", str(tmp_path / "drive"))
    monkeypatch.setattr(cli, "listener_pid", lambda port: None)  # never touch the real process table in tests


@pytest.mark.parametrize("cmd", ["ui", "web", "app", "scan", "ask hi", "caption"])
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

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, env=None: FakePopen(lambda: calls.append((cmd, env))))
    assert cli.main(["secure-ui", "--port", "9100", "--no-browser"]) == 0
    cmd, env = calls[0]
    assert cmd[0].endswith("scripts/aperture-sandboxed.sh") and cmd[1] == str(photos) and cmd[2] == str(exports)
    assert cmd[3:] == ["--", cli.sys.executable, "-m", "aperture", "web", "--port", "9100"]
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

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, env=None: FakePopen(lambda: seen.append(env)))
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

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, env=None: FakePopen(lambda: calls.append(cmd)))
    return calls


@pytest.mark.parametrize(
    "command,expected",
    [
        ("/x/.venv/bin/python -m aperture ui --port 8765", True),
        ("/x/.venv/bin/python -m aperture web --port 8765", True),
        ("/x/.venv/bin/python /x/.venv/bin/aperture ui", True),
        ("python /x/src/aperture/ui/app.py", True),
        ("/bin/bash /x/scripts/aperture-sandboxed.sh /p -- python -m aperture ui", True),
        ("python -m http.server 8765", False),
        ("/x/.venv/bin/python -m aperture scan", False),
        ("/x/.venv/bin/aperture caption", False),
        ("/usr/bin/ssh -L 8765:localhost:8765 host", False),
        ("", False),
    ],
)
def test_only_aperture_web_servers_are_recognised(command, expected):
    assert cli.is_aperture_ui(command) is expected


def test_stop_process_asks_politely_then_forces(monkeypatch):
    import signal
    import time

    sent, alive = [], {"v": True}

    def fake_kill(pid, sig):
        sent.append(sig)
        if sig == signal.SIGKILL:
            alive["v"] = False
        if sig == 0 and not alive["v"]:
            raise ProcessLookupError

    clock = iter(range(0, 10_000))
    monkeypatch.setattr(cli.os, "kill", fake_kill)
    monkeypatch.setattr(time, "monotonic", lambda: next(clock) * 5.0)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert cli.stop_process(111, wait=8.0) is True
    assert sent[:2] == [signal.SIGCONT, signal.SIGTERM] and signal.SIGKILL in sent
    sent.clear()
    alive["v"] = False  # already gone
    assert cli.stop_process(111) is True


def test_stop_old_ui_only_stops_aperture_and_forgets_the_pid_file(monkeypatch, tmp_path):
    stopped = []
    monkeypatch.setattr(cli, "stop_process", lambda pid, wait=8.0: stopped.append(pid) or True)
    pid_file = tmp_path / "ui.pid"
    pid_file.write_text("4242")
    monkeypatch.setattr(
        cli, "command_of", lambda pid: "python -m aperture ui --port 8765" if pid == 4242 else "python -m http.server"
    )
    monkeypatch.setattr(cli, "listener_pid", lambda port: 9999)
    said = cli.stop_old_ui(pid_file, 8765)
    assert (
        stopped == [4242] and "Stopped the older Aperture" in said[0] and not pid_file.exists()
    )  # 9999 is not Aperture: left alone


def test_secure_ui_reuses_8765_by_stopping_the_old_aperture(monkeypatch, tmp_path, capsys):
    calls = _secure_setup(monkeypatch, tmp_path)
    state = {"stopped": False}
    monkeypatch.setattr(cli, "listener_pid", lambda port: None if state["stopped"] else 777)
    monkeypatch.setattr(cli, "command_of", lambda pid: "python /x/.venv/bin/aperture ui")
    monkeypatch.setattr(cli, "stop_process", lambda pid, wait=8.0: state.update(stopped=True) or True)
    monkeypatch.setattr(cli, "port_is_free", lambda port: state["stopped"])
    assert cli.main(["secure-ui", "--no-browser"]) == 0
    assert calls[0][-2:] == ["--port", "8765"] and "Stopped the older Aperture" in capsys.readouterr().out


def test_secure_ui_leaves_other_programs_alone_and_uses_the_next_port(monkeypatch, tmp_path, capsys):
    calls = _secure_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "listener_pid", lambda port: 888 if port == 8765 else None)
    monkeypatch.setattr(cli, "command_of", lambda pid: "python -m http.server 8765")
    stopped = []
    monkeypatch.setattr(cli, "stop_process", lambda pid, wait=8.0: stopped.append(pid) or True)
    monkeypatch.setattr(cli, "port_is_free", lambda port: port != 8765)
    assert cli.main(["secure-ui", "--no-browser"]) == 0
    assert not stopped and calls[0][-2:] == ["--port", "8766"] and "another program" in capsys.readouterr().out


def test_explicit_port_used_by_another_program_is_refused(monkeypatch, tmp_path, capsys):
    calls = _secure_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "port_is_free", lambda port: False)
    monkeypatch.setattr(cli, "command_of", lambda pid: "")
    assert cli.main(["secure-ui", "--port", "9100", "--no-browser"]) == 2
    assert not calls and "Leave out --port" in capsys.readouterr().out


def test_the_running_copy_is_remembered_and_forgotten(monkeypatch, tmp_path):
    from aperture.config import Paths

    _secure_setup(monkeypatch, tmp_path)
    pid_file = Paths(tmp_path / "drive").data / "ui.pid"
    seen = {}

    class Watching(FakePopen):
        def wait(self):
            seen["during"] = pid_file.read_text()
            return 0

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda cmd, env=None: Watching(lambda: None))
    monkeypatch.setattr(cli, "port_is_free", lambda port: True)
    assert cli.main(["secure-ui", "--no-browser"]) == 0
    assert seen["during"] == "424242" and not pid_file.exists()


def test_browser_opens_once_the_server_answers(monkeypatch):
    import time
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
    monkeypatch.setattr(time, "sleep", lambda s: None)
    cli.open_when_ready(8770)
    assert opened == ["http://127.0.0.1:8770"]


def test_stop_process_wakes_a_suspended_copy_before_asking_it_to_stop(monkeypatch):
    import signal
    import time

    sent, alive = [], {"v": True}

    def fake_kill(pid, sig):
        sent.append(sig)
        if sig == signal.SIGTERM:
            alive["v"] = False
        if sig == 0 and not alive["v"]:
            raise ProcessLookupError

    monkeypatch.setattr(cli.os, "kill", fake_kill)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert cli.stop_process(5) is True
    assert sent[:2] == [signal.SIGCONT, signal.SIGTERM]


def test_secure_ui_can_start_the_classic_screens(monkeypatch, tmp_path):
    calls = _secure_setup(monkeypatch, tmp_path)
    monkeypatch.setattr(cli, "port_is_free", lambda port: True)
    assert cli.main(["secure-ui", "--classic", "--no-browser"]) == 0
    assert calls[0][-4:-2] == ["aperture", "ui"]


def test_installing_the_start_up_service_is_allowed_outside_the_sandbox_because_it_only_writes_a_start_up_file():
    assert "install-service" not in cli.GUARDED and "install-launcher" not in cli.GUARDED
