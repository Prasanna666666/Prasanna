# Aperture in Docker

Two ways to run Aperture safely. Pick one.

| | Native + macOS sandbox | Docker container |
|---|---|---|
| Speed (CLIP/faces) | Fast: Apple GPU | Slow: CPU only (hours to days for a big library) |
| Text in photos (OCR) | Yes: Apple Vision | **No** (PDFs and text files still work) |
| Isolation | Kernel sandbox: no network, photos read-only | Separate network with no internet, read-only photos, only 3 folders visible |
| Setup | `scripts/aperture-sandboxed.sh` | `docker-compose.aperture.yml` |

Docker on a Mac runs a Linux VM, so Apple Vision and the GPU are unavailable inside it. If you care about search speed
and photo text search, use the sandbox. If you care most about isolation, use Docker.

## Run
```bash
export APERTURE_HOST_DRIVE=/Volumes/YourDrive           # if not /Volumes/Expansion
mkdir -p "$APERTURE_HOST_DRIVE"/{Aperture,Aperture_Exports}
ollama pull llama3.2:3b                                  # native Ollama on the Mac (uses the GPU)
docker compose -f docker-compose.aperture.yml build
docker compose -f docker-compose.aperture.yml --profile setup run --rm fetch-models   # once; the only internet use
docker compose -f docker-compose.aperture.yml up -d                                    # open http://127.0.0.1:8765
```
Docker Desktop: Settings > Resources > Memory about 4 GB (the Aperture container is capped at 5 GB; Ollama runs natively).

## What the container can and cannot touch
- Sees **only** `Aperture/` (index, thumbnails, models; read-write), `Aperture_Exports/` (read-write) and `Photos/` (**read-only**).
  Nothing else on your drive or Mac is visible.
- Photo moves ("Tidy up" > move duplicates) fail by design because the photos are read-only. Use the native app for that.
- No route to the internet: internal network; the only outside network belongs to the one-off `fetch-models` job.
- Python-level guard stays on, trusting just one extra name: `ollama` (a byte forwarder to your Mac's Ollama).
- Non-root user, read-only root filesystem, all capabilities dropped, UI published on 127.0.0.1 only.

## Verify
```bash
docker compose -f docker-compose.aperture.yml exec aperture python -c "import urllib.request as u; u.urlopen('https://example.com')"   # must fail
docker compose -f docker-compose.aperture.yml exec aperture sh -c "touch /Volumes/Expansion/Photos/x"                                   # must fail (read-only)
```

## Not covered
- Encrypt the drive (Finder > right-click > Encrypt) and keep FileVault on; Docker does not encrypt your data.
- Untested on a real Mac: this was written without a Docker engine. If a step fails, send only the error text.
- A Linux OCR engine (so photo text search works in Docker) is a possible later addition.
