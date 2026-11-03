import json
import os
import socket
from pathlib import Path

import pytest

from aperture.config import ENV_INTERNAL
from aperture.export import build_plan, create_job, run_export, run_job, sanitize_folder_name
from aperture.safety import (
    SafetyError,
    WriteGuard,
    drive_problem,
    enable_offline_guard,
    is_local_host,
    resolve_export_dir,
    resolve_photo_dir,
)


def test_missing_drive_reported(tmp_path):
    assert "not found" in drive_problem(tmp_path / "nope")


def test_internal_disk_rejected_unless_overridden(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_INTERNAL)
    assert "internal" in drive_problem(tmp_path)


def test_export_dir_may_sit_in_source_but_not_in_data(ctx):
    s = ctx.settings
    resolve_export_dir(ctx.paths, str(s.photo_dir) + "/sub", s.photo_dir)
    with pytest.raises(PermissionError):
        resolve_export_dir(ctx.paths, str(ctx.paths.root / "x"), s.photo_dir)
    with pytest.raises(PermissionError):
        resolve_photo_dir(ctx.paths, "/etc")


def test_write_guard_blocks_outside_paths(ctx, tmp_path):
    guard = WriteGuard(ctx.paths)
    with pytest.raises(SafetyError):
        guard.check(tmp_path / "elsewhere.txt")
    guard.check(ctx.paths.data / "ok.txt")


def test_offline_guard_blocks_remote_allows_loopback():
    enable_offline_guard()
    assert is_local_host("127.0.0.1") and not is_local_host("example.com")
    with pytest.raises(OSError):
        socket.create_connection(("example.com", 80), timeout=1)


def test_export_copies_verifies_and_is_idempotent(scanned):
    conn = scanned.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items ORDER BY id")]
    originals = {r[0]: Path(r[0]).read_bytes() for r in conn.execute("SELECT path FROM items")}
    plan = build_plan(conn, scanned.paths, scanned.settings, ids, "Trip: Italy/2021")
    assert plan.count == 5 and plan.folder.name == sanitize_folder_name("Trip: Italy/2021")
    report = run_export(plan, scanned.paths, scanned.settings)
    assert report.copied == 5 and not report.failed
    again = run_export(
        build_plan(conn, scanned.paths, scanned.settings, ids, "Trip: Italy/2021"), scanned.paths, scanned.settings
    )
    assert again.copied == 0 and again.skipped_identical == 5
    assert (plan.folder / "manifest.json").is_file()
    assert {p: Path(p).read_bytes() for p in originals} == originals


def test_export_never_overwrites_different_file(scanned):
    conn = scanned.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items LIMIT 1")]
    plan = build_plan(conn, scanned.paths, scanned.settings, ids, "Clash")
    plan.folder.mkdir(parents=True)
    name = os.path.basename(plan.entries[0].source)
    (plan.folder / name).write_bytes(b"different")
    report = run_export(plan, scanned.paths, scanned.settings)
    assert report.copied == 1
    assert (plan.folder / name).read_bytes() == b"different"
    assert len(list(plan.folder.glob("*.jpg"))) == 2


def test_background_job_roundtrip(scanned):
    conn = scanned.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items")]
    job_id = create_job(scanned.paths, ids, "Job")
    run_job(scanned.paths, scanned.settings, conn, job_id)
    job = json.loads((scanned.paths.jobs / f"{job_id}.json").read_text())
    assert job["state"] == "done" and job["done"] == 5


def test_scan_skips_export_folder(tmp_path):
    from aperture.indexing.discovery import discover

    (tmp_path / "exp").mkdir()
    (tmp_path / "exp" / "copy.jpg").write_bytes(b"x")
    (tmp_path / "keep.jpg").write_bytes(b"x")
    names = [f.path.rsplit("/", 1)[-1] for f in discover(tmp_path, skip=[tmp_path / "exp"])]
    assert names == ["keep.jpg"]


def test_trusted_hosts_default_empty_and_parse(monkeypatch):
    from aperture.safety import trusted_hosts

    monkeypatch.delenv("APERTURE_TRUSTED_HOSTS", raising=False)
    assert trusted_hosts() == set()
    monkeypatch.setenv("APERTURE_TRUSTED_HOSTS", " Ollama , ,bridge")
    assert trusted_hosts() == {"ollama", "bridge"}


def test_ollama_url_env_and_ui_host_env(monkeypatch, tmp_path):
    from aperture.config import Paths, Settings

    monkeypatch.setenv("APERTURE_OLLAMA_URL", "http://ollama:11434")
    assert Settings.defaults(Paths(tmp_path)).ollama_url == "http://ollama:11434"
    monkeypatch.delenv("APERTURE_OLLAMA_URL")
    assert Settings.defaults(Paths(tmp_path)).ollama_url == "http://127.0.0.1:11434"


def test_never_online_beats_allow_network(monkeypatch):
    from aperture.config import ENV_NEVER_ONLINE, ENV_ONLINE, online_allowed

    monkeypatch.setenv(ENV_ONLINE, "1")
    monkeypatch.delenv(ENV_NEVER_ONLINE, raising=False)
    assert online_allowed() is True
    monkeypatch.setenv(ENV_NEVER_ONLINE, "1")
    assert online_allowed() is False


def test_fetch_models_refused_when_locked(monkeypatch, tmp_path, capsys):
    from aperture.cli import main

    monkeypatch.setenv("APERTURE_NEVER_ONLINE", "1")
    monkeypatch.setenv("APERTURE_DRIVE", str(tmp_path))
    assert main(["fetch-models"]) == 2
    assert "permanently disabled" in capsys.readouterr().out


def test_single_mistral_model_and_old_settings_migrate(tmp_path):
    import json

    from aperture.config import Paths, Settings

    paths = Paths(tmp_path)
    d = Settings.defaults(paths)
    assert d.ollama_model == d.vision_model == "ministral-3:3b"
    paths.settings_file.parent.mkdir(parents=True, exist_ok=True)
    paths.settings_file.write_text(json.dumps({"schema": 3, "ollama_model": "llama3.2:3b", "vision_model": "moondream",
                                                "page_size": 48}))
    s = Settings.load(paths)
    assert s.ollama_model == s.vision_model == "ministral-3:3b" and s.page_size == 48 and s.schema == 8


def test_doctor_skips_slow_stats_unless_asked(monkeypatch, tmp_path, capsys):
    from aperture import cli

    monkeypatch.setenv("APERTURE_DRIVE", str(tmp_path))
    monkeypatch.setenv("APERTURE_ALLOW_INTERNAL", "1")
    called = []
    monkeypatch.setattr(cli, "_stats", lambda conn: called.append(1) or {"photos": 0})
    ns = cli.build_parser().parse_args(["doctor"])
    assert ns.stats is False and cli.build_parser().parse_args(["doctor", "--stats"]).stats is True
