import os
import sys

from .registry import ManifestError
from .server import build, serve

if __name__ == "__main__":
    try:
        atlas = build()
    except ManifestError as exc:
        sys.exit(f"Atlas cannot start: {exc}")
    sys.exit(serve(atlas, os.environ.get("ATLAS_HOST", "127.0.0.1"), int(os.environ.get("ATLAS_PORT", "8000"))))
