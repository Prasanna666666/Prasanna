#!/bin/bash
# The one look lives in design/design.css; every app serves its own copy next to its stylesheet. Run after editing it.
set -euo pipefail
cd "$(dirname "$0")/.."
npx --yes prettier@3.8.1 --write design/design.css >/dev/null   # the same formatting as the rest of the web code
for dir in atlas/src/atlas/static finance/src/finance/static library/src/library/static; do
  cp design/design.css "$dir/design.css"
done
echo "design.css copied to Atlas, Finance and Documents"
