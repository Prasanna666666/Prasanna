"""One answer to "which model": an app's own setting wins, then ATLAS_MODEL, then the default; no app picks a model any other way."""

import re
from pathlib import Path

import pytest

from kit import config, llm

ROOT = Path(__file__).resolve().parents[2]


def test_the_default_when_nothing_is_set(monkeypatch):
    monkeypatch.delenv("ATLAS_MODEL", raising=False)
    assert config.model() == llm.DEFAULT_MODEL == config.model("") == config.model("   ") == config.model(None)


def test_the_shared_environment_choice_beats_the_default(monkeypatch):
    monkeypatch.setenv("ATLAS_MODEL", "ministral-3:8b")
    assert config.model() == "ministral-3:8b" and llm.configured_model() == "ministral-3:8b"


def test_an_apps_own_setting_beats_the_shared_choice(monkeypatch):
    monkeypatch.setenv("ATLAS_MODEL", "ministral-3:8b")
    assert config.model("other:7b") == "other:7b"


@pytest.mark.parametrize("package", ["finance", "library", "atlas"])
def test_no_app_picks_the_default_model_by_itself(package):
    """An app that read `llm.DEFAULT_MODEL` directly would ignore ATLAS_MODEL; they must ask kit.config."""
    offenders = []
    for path in (ROOT / package / "src").rglob("*.py"):
        if re.search(r"\bllm\.DEFAULT_MODEL\b|\bDEFAULT_MODEL\b", path.read_text()):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
