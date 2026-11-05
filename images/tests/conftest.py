"""Shared fixtures for the picture engine's tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from images.config import ENV_INTERNAL, Paths


@pytest.fixture(autouse=True)
def _allow_internal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_INTERNAL, "1")  # tmp dirs live on the internal disk in CI


@pytest.fixture
def paths(tmp_path: Path) -> Paths:
    p = Paths(drive=tmp_path / "drive")
    p.drive.mkdir()
    p.ensure()
    return p
