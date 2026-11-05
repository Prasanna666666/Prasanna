#!/bin/bash
# Stop Finance. Your data stays in its Docker volume (nothing is deleted).
cd "$(dirname "$0")/.."
docker compose down
