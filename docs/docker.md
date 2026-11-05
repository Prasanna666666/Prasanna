# Aperture in Docker

Two ways to run Aperture safely. Pick one.

| | Native + macOS sandbox | Docker container |
|---|---|---|
| Speed (CLIP/faces) | Fast: Apple GPU | Slow: CPU only (hours to days for a big library) |
| Text in photos (OCR) | Yes: Apple Vision | Yes: Tesseract (English and Dutch; a little less accurate than Apple Vision) |
| Isolation | Kernel sandbox: no network (also locked in code), photos read-only | Internal network, no download job, locked in code, read-only photos, only 3 folders visible |
| Setup | `scripts/aperture-sandboxed.sh` | `docker-compose.aperture.yml` |

Docker on a Mac runs a Linux VM, so Apple Vision and the GPU are unavailable inside it: text in photos is read by Tesseract instead, and the picture models run on the CPU. If you care about indexing speed, use the sandbox. If you care most about isolation, use Docker.

## Disk space
The Docker image includes PyTorch and is several GB, and Docker Desktop keeps its own disk file. On a Mac that is short of space, the
native install + sandbox is much lighter. Models: one only (`ministral-3:3b`). Free space with `ollama list` then `ollama rm <name>`,
and `docker system prune -a` to clear unused images (careful: removes all unused images).

## Run
```bash
export APERTURE_HOST_DRIVE=/Volumes/YourDrive           # if not /Volumes/Expansion
mkdir -p "$APERTURE_HOST_DRIVE"/{Aperture,Aperture_Exports}
ollama pull ministral-3:3b                                  # native Ollama on the Mac (uses the GPU)
# Models for Aperture itself (CLIP, faces, place data) must already be in $APERTURE_HOST_DRIVE/Aperture/models.
# Get them once with the normal install (scripts/install.sh -> `aperture fetch-models`). The container cannot download.
scripts/up.sh   # builds and starts Lumo (the fast web app)
# or by hand: docker compose -f docker-compose.aperture.yml up -d --build                                    # open http://127.0.0.1:8765
```
Docker Desktop: Settings > Resources > Memory about 4 GB (the Aperture container is capped at 5 GB; Ollama runs natively).

## What the container can and cannot touch
- Sees **only** `Aperture/` (index, thumbnails, models; read-write), `Aperture_Exports/` (read-write) and `Photos/` (**read-only**).
  Nothing else on your drive or Mac is visible.
- Photo moves ("Tidy up" > move duplicates) fail by design because the photos are read-only. Use the native app for that.
- **No internet, ever.** Internal network only, no download job, and `APERTURE_NEVER_ONLINE=1` makes the code refuse to enable the network
  (even `aperture fetch-models` is refused inside). Building the image needs the internet once (Docker, not Aperture).
- Python-level guard stays on, trusting just one extra name: `ollama` (a byte forwarder to your Mac's Ollama).
- Non-root user, read-only root filesystem, all capabilities dropped, UI published on 127.0.0.1 only.

## Verify
```bash
docker compose -f docker-compose.aperture.yml exec aperture python -c "import urllib.request as u; u.urlopen('https://example.com')"   # must fail
docker compose -f docker-compose.aperture.yml exec aperture sh -c "touch /Volumes/Expansion/Photos/x"                                   # must fail (read-only)
```

## Honest limits
- The two forwarder containers (`gateway`, `ollama`) sit on Docker's default network so the page can be shown and Ollama reached.
  They only copy bytes and run no Aperture code; the Aperture container itself has no route out.
- Ollama is installed on the Mac, outside Docker: turn off its update checks, or block it in a firewall (LuLu / Little Snitch),
  or switch Wi-Fi off while using Aperture for a hard guarantee.

## Not covered
- Theft or loss of the computer is out of scope (so no FileVault or drive encryption is needed). Docker does not encrypt your data.
- Untested on a real Mac: this was written without a Docker engine. If a step fails, send only the error text.
- Tesseract needs its language packs: the image installs English and Dutch. Add more in `Dockerfile.aperture` (`tesseract-ocr-<lang>`).

- The container now starts Lumo's fast web app (`aperture web`). The older screens: `docker compose -f docker-compose.aperture.yml run --rm --service-ports aperture ui`.
- Not built or run in the sandbox this was written in (no Docker daemon there): the first build on your Mac is the first real test.
