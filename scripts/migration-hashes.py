"""Prints a hash of every migration step of every module: python scripts/migration-hashes.py [repository root]. `kit/tests/test_migrations_frozen.py` compares it with the recorded list, so a step that was released is never edited (only new steps are appended)."""

import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root / p / "src") for p in ("kit", "finance", "library", "images", "atlas")]
sys.meta_path = [finder for finder in sys.meta_path if "editable" not in repr(finder).lower()]  # an installed copy of another checkout must not win over the one asked for


def digest(step: str) -> str:
    return hashlib.sha256(step.encode()).hexdigest()[:16]


def collect() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    from finance.modules import ALL

    for module in ALL:
        out[f"finance:{module.name}"] = [digest(s) for s in module.migrations]
    from library import store

    out[f"library:{store.MODULE.name}"] = [digest(s) for s in store.MODULE.migrations]
    from images import db as images_db

    out["images:index"] = [digest(s) for s in images_db.MIGRATIONS]
    return out


if __name__ == "__main__":
    print(json.dumps(collect(), indent=1, sort_keys=True))
