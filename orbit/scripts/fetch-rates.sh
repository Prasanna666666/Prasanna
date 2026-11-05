#!/bin/bash
# Download the ECB's daily euro reference rates (the whole history) into your finance folder. The ONLY step of Finance that goes online, and it is not part
# of the Finance app: run it yourself on the Mac. Afterwards press "Read my files" in Finance: it loads the rates and converts your payments to euros.
#   ./scripts/fetch-rates.sh                         # into ~/OrbitFinance
#   ./scripts/fetch-rates.sh "/path/to/finance folder"
set -euo pipefail
DEST="${1:-${ORBIT_FINANCE_DIR:-$HOME/OrbitFinance}}"
mkdir -p "$DEST"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
echo "Downloading the ECB exchange rates ..."
curl -fsSL --max-time 90 -o "$TMP/rates.zip" https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip \
  || { echo "Could not download. Get 'eurofxref-hist.csv' from the ECB's euro foreign exchange reference rates page and put it in $DEST"; exit 1; }
unzip -o -q "$TMP/rates.zip" -d "$TMP"
mv "$TMP/eurofxref-hist.csv" "$DEST/ecb-eurofxref-hist.csv"
echo "Saved $DEST/ecb-eurofxref-hist.csv. Now open Finance and press Read my files."
