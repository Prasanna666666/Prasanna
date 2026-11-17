"""A migration step that has been released is never edited, reordered or removed: only new steps are appended. The recorded hashes are those of the steps at the start of the review round
(`scripts/migration-hashes.py` prints them); a step added later is simply not in the list yet, and is added to it with the same script."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _current() -> dict[str, list[str]]:
    spec = importlib.util.spec_from_file_location("migration_hashes", ROOT / "scripts" / "migration-hashes.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.collect()


def test_no_released_migration_step_was_edited_reordered_or_removed():
    recorded = json.loads((Path(__file__).with_name("migration_hashes.json")).read_text())
    current = _current()
    for module, steps in recorded.items():
        assert module in current, f"the module {module} lost its migrations"
        assert current[module][: len(steps)] == steps, f"a released step of {module} was changed: add a new step instead of editing an old one"


def test_the_check_notices_an_edited_step():
    recorded = json.loads((Path(__file__).with_name("migration_hashes.json")).read_text())
    module = next(m for m, steps in recorded.items() if steps)
    edited = {**_current(), module: ["0" * 16, *_current()[module][1:]]}
    assert edited[module][: len(recorded[module])] != recorded[module]
