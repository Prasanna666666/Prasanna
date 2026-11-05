import os
import sys

from .registry import ManifestError
from .server import build, serve

if __name__ == "__main__":
    try:
        hub = build()
    except ManifestError as exc:
        sys.exit(f"Home cannot start: {exc}")
    sys.exit(serve(hub, os.environ.get("HUB_HOST", "127.0.0.1"), int(os.environ.get("HUB_PORT", "8000"))))
