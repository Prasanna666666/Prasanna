"""Real personal data must never be inside the repository."""

import subprocess
from pathlib import Path

from orbit import db

ROOT = Path(__file__).parent.parent
FORBIDDEN = {".db", ".sqlite", ".sqlite3", ".csv", ".xlsx", ".xls", ".pdf", ".ofx", ".qif", ".mbox", ".eml"}


def test_no_data_files_tracked_in_git():
    r = subprocess.run(["git", "ls-files", "."], cwd=ROOT, capture_output=True, text=True, check=False)
    files = r.stdout.split() if r.returncode == 0 else [str(p) for p in ROOT.rglob("*") if ".git" not in p.parts]
    bad = [f for f in files if Path(f).suffix.lower() in FORBIDDEN or "OrbitInbox" in f]
    assert not bad, bad


def test_default_data_home_is_outside_the_project(monkeypatch):
    monkeypatch.delenv("ORBIT_HOME", raising=False)
    assert ROOT.resolve() not in db.home().resolve().parents and db.home().resolve() != ROOT.resolve()
