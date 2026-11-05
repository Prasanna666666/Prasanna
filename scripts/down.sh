#!/bin/bash
# Stop Lumo. Your data stays in its Docker volume (nothing is deleted).
cd "$(dirname "$0")/.."
docker compose -f docker-compose.aperture.yml down
