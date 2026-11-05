#!/bin/bash
# Run before every push: compile everything, catch undefined names and unused imports, run all tests.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m compileall -q src
ruff check src --select F,E9 --no-cache
python -m pytest -q -p no:cacheprovider
echo "ALL CHECKS PASSED"
