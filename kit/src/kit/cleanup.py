"""Remove the plain-text copies an older release left beside encrypted databases:  python -m kit.cleanup [folder]
Identical copies are removed at once. A copy that differs from the encrypted file is removed only if you type yes for that file."""

from __future__ import annotations

import sys
from pathlib import Path

from . import db


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    key = db.database_key()
    if key is None:
        print("No database key is set (ATLAS_DB_KEY or ATLAS_DB_KEY_FILE): nothing can be checked, so nothing was removed.")
        return 1
    folder = Path(args[0]) if args else db.home()
    found = db.leftover_plain_copies(folder)
    if not found:
        print(f"No plain-text copies in {folder}.")
        return 0
    for held in found:
        print(db.retire_leftover(held, key, lambda question: input(question + " Type yes: ").strip().lower() == "yes"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
