"""The sealed picture indexer: no network, photos read-only, writes only the index.

It waits for a request from the Documents service (a small file), reads every new or changed picture with the shared engine, and reports where it is
in another small file. Models come from the drive and are never downloaded here."""

from __future__ import annotations

import sys
import threading
import time

from images.indexing.runner import Scanner

from . import pictures

POLL_SECONDS = 2


def run_once(engine) -> str:
    """One scan. The state file says it is running, how far it is, and what it did."""
    pictures.write_state(engine, True, "Reading pictures…")
    stop = threading.Event()
    try:
        done = Scanner(engine.paths, engine.settings, engine.db, engine.services_for_stage, stop).run()
        summary = pictures.summarise(engine, done)
    except Exception as exc:  # noqa: BLE001 - reported to the person pressing Update, never lost
        summary = f"Pictures could not be read: {type(exc).__name__}"
    pictures.write_state(engine, False, "", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    engine = pictures.build_engine()
    if "--once" in args:
        print(run_once(engine), flush=True)
        return 0
    wake = pictures._control(engine) / pictures.WAKE
    while True:
        if wake.exists():
            wake.unlink(missing_ok=True)
            print(run_once(engine), flush=True)
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
