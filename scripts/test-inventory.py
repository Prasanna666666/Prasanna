"""Prints the per-file test inventory that docs/testing.md carries, counted by pytest itself:  python scripts/test-inventory.py
Each package is collected with its own interpreter if ATLAS_PYTHONS names one ("kit=/path/python,finance=/path/python"), otherwise with this one.
The totals are the sums of the rows, so the table and the package totals cannot disagree."""

import collections
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ("kit", "images", "finance", "library", "atlas")


def interpreters() -> dict[str, str]:
    given = dict(item.split("=", 1) for item in os.environ.get("ATLAS_PYTHONS", "").split(",") if "=" in item)
    return {p: given.get(p, sys.executable) for p in PACKAGES}


def collect(package: str, python: str) -> dict[str, int]:
    out = subprocess.run([python, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"], cwd=ROOT / package, capture_output=True, text=True, check=False).stdout
    files: collections.Counter[str] = collections.Counter()
    for line in out.splitlines():
        if "::" in line:
            files[line.split("::")[0]] += 1
    return dict(sorted(files.items()))


def main() -> None:
    found = {p: collect(p, py) for p, py in interpreters().items()}
    print("| Package | Tests |\n|---|---|")
    for package, files in found.items():
        print(f"| {package} | {sum(files.values())} |")
    print(f"| **Total** | **{sum(sum(f.values()) for f in found.values())}** |\n")
    for package, files in found.items():
        print(f"### {package} ({sum(files.values())})\n\n| File | Tests |\n|---|---|")
        for name, count in files.items():
            print(f"| `{package}/{name}` | {count} |")
        print()


if __name__ == "__main__":
    main()
