"""Scan CI artefacts (test logs, JUnit reports, SBOMs, anything the workflow uploads) for the synthetic personal-content sentinels and the test keys.

Usage: python tools/scan_artefacts.py FILE_OR_DIR...   Exit 0 if every file is clean, 1 if any sentinel is found (the file and sentinel NAME are printed, never the surrounding text).
Plan criterion 9: sentinel scans find no personal content, source names, subjects/addresses, prompts or secrets in logs and CI artefacts.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))


def sentinels() -> tuple[str, ...]:
    from conftest import ALL_SENTINELS  # the same list the in-process redaction tests use

    return tuple(ALL_SENTINELS)


def scan(paths: list[Path], needles: tuple[str, ...]) -> list[tuple[str, int]]:
    """(file, index of the sentinel) for every hit; the sentinel text itself is not reported."""
    hits: list[tuple[str, int]] = []
    for root in paths:
        for path in sorted(root.rglob("*") if root.is_dir() else [root]):
            if not path.is_file():
                continue
            data = path.read_bytes()
            hits += [(str(path), i) for i, needle in enumerate(needles) if needle.encode() in data]
    return hits


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv]
    if not paths or not all(p.exists() for p in paths):
        print("scan_artefacts: nothing to scan or a path is missing", file=sys.stderr)
        return 2
    needles = sentinels()
    hits = scan(paths, needles)
    for file, index in hits:
        print(f"sentinel #{index} found in {file}")
    scanned = sum(1 for p in paths for f in (p.rglob("*") if p.is_dir() else [p]) if f.is_file())
    print(f"scan_artefacts: {scanned} files scanned, {len(hits)} sentinel hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
