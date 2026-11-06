#!/bin/bash
# Stop Atlas. Your data stays where it is; nothing is deleted.
cd "$(dirname "$0")"
atlas/down.sh
library/scripts/down.sh
finance/scripts/down.sh
