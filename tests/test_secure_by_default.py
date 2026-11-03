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
    assert cli.main(["secure-ui", "--port", "9100"]) == 0
    cmd, env = calls[0]
    assert cmd[0].endswith("scripts/aperture-sandboxed.sh") and cmd[1] == str(photos) and cmd[2] == str(exports)
    assert cmd[3:] == ["--", cli.sys.executable, "-m", "aperture", "ui", "--port", "9100"]
    assert env["ALLOW_MOVES"] == "no"
    cli.main(["secure-ui", "--allow-moves"])
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
