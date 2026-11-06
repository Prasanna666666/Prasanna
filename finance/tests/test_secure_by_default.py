"""Finance's data commands refuse to open an unencrypted database unless explicitly allowed."""

import pytest

from finance import cli


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for v in ("ATLAS_DB_KEY", "ATLAS_DB_KEY_FILE", "ATLAS_ALLOW_PLAIN"):
        monkeypatch.delenv(v, raising=False)


@pytest.mark.parametrize("cmd", ["ui", "brief", "tag", "import-notes"])
def test_refuses_without_the_key(cmd, capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    assert cli.main([cmd]) == 2
    out = capsys.readouterr().out
    assert "without encryption" in out and "./scripts/up.sh" in out and "ATLAS_ALLOW_PLAIN=1" in out
    assert not list(tmp_path.iterdir())  # no database was created


def test_key_or_explicit_override_allows_it(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    monkeypatch.setenv("ATLAS_ALLOW_PLAIN", "1")
    assert cli.main(["tools"]) == 0  # not guarded at all
    assert cli.main(["brief"]) == 0 and '"tasks_due"' in capsys.readouterr().out
    monkeypatch.delenv("ATLAS_ALLOW_PLAIN")
    monkeypatch.setenv("ATLAS_DB_KEY", "k")
    assert cli.secure_ok()


def test_listing_the_tools_never_creates_a_database(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("ATLAS_HOME", str(tmp_path))
    assert cli.main(["tools"]) == 0
    assert "money" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())
