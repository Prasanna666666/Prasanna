#!/bin/bash
# Stop Home. The apps keep running and keep their data.
cd "$(dirname "$0")"
docker compose down
