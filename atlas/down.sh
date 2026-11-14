#!/bin/bash
# Stop Atlas. The apps keep running and keep their data.
cd "$(dirname "$0")"
export PLATFORM_KEY="${PLATFORM_KEY:-stopping}"  # stopping needs no key, but compose insists on a value
docker compose down
