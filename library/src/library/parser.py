"""The isolated parser: turns untrusted files (PDF incl. scans, images, spreadsheets, Word, web pages, emails, JSON, ZIP, CSV, text) into one plain JSON shape. It is the only code that opens them.

Runs in its own container with NO network, the inbox mounted read-only, and a single writable output folder that the
app mounts read-only. Each file is parsed in a throw-away subprocess with CPU, memory and time limits, so a hostile or
broken file can at worst fail that one file. Output is JSON only (never pickle), text capped and stripped of control
characters; the app still treats it as untrusted data.

    library-parser --once  [--inbox /inbox --out /parsed]
    library-parser --watch
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from pathlib import Path

from . import batch, control, extraction, readers, rounds


def _arguments() -> argparse.ArgumentParser:
    """The command line: where to read, where to write, and the modes (watch, once, check one file)."""
    ap = argparse.ArgumentParser(prog="library-parser")
    ap.add_argument("--inbox", default=os.environ.get("ATLAS_INBOX", str(Path.home() / "AtlasInbox")))
    ap.add_argument("--out", default=os.environ.get("ATLAS_PARSED", str(Path.home() / "AtlasParsed")))
    ap.add_argument(
        "--collection",
        action="append",
        default=[c for c in os.environ.get("LIBRARY_COLLECTIONS", "").split(",") if c],
        help="NAME=PATH: a folder you keep for one purpose (finance=/finance, health=/health), read-only; its files are always read and carry that name",
    )
    ap.add_argument(
        "--mail",
        default=os.environ.get("ATLAS_MAIL", ""),
        help="Apple Mail's own folder (read-only): only the mailboxes declared in mailboxes.json (Inbox and Sent)",
    )
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--extract-one", metavar="FILE", help=argparse.SUPPRESS)
    ap.add_argument(
        "--check",
        nargs="?",
        const=0,
        type=int,
        metavar="N",
        help="read every file (or an even sample of N) without storing anything and print what came out, by kind of file",
    )
    return ap


def _one_round(a: argparse.Namespace, out: Path) -> dict:
    """One round of reading: wait for the person's request when watching, read everything, leave what could not be read for the report."""
    out.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        (out / ".ocr-engine").write_text(
            "apple" if readers.apple_ocr_running() else "tesseract"
        )  # which text recognition the pages are read with: the Documents service re-reads old scans once it is Apple's
    if a.watch:
        rounds._wait_for_next_round(out)  # nothing is read until the person asks (so starting the computer never starts a big read)
    (out / control.STOP).unlink(missing_ok=True)
    (out / rounds.BUSY).touch()  # tells the Documents service that more may still be coming
    try:
        res = rounds.read_everything(a)
    finally:
        (out / rounds.BUSY).unlink(missing_ok=True)
        (out / ".now").unlink(missing_ok=True)
    (out / rounds.FAILED_FILE).write_text(json.dumps(batch._FAILED[: batch.MAX_FAILED]))  # what could not be read this round, for the report
    batch._FAILED.clear()
    return res


def main(argv: list[str] | None = None) -> int:
    a = _arguments().parse_args(argv)
    if a.check is not None:
        from . import selfcheck

        roots = [("inbox", Path(a.inbox)), *rounds.collections(a.collection)]
        print(selfcheck.render(selfcheck.check(roots, a.check)))
        return 0
    if a.extract_one:
        extraction._limits()  # the child limits itself before it opens the file (a limit set by the parent needs preexec_fn, which is unsafe with threads)
        sys.stdout.write(json.dumps(extraction.extract(Path(a.extract_one)), ensure_ascii=False))
        return 0
    out = Path(a.out)
    with contextlib.suppress(OSError):
        os.nice(10)  # reading is never more important than what the person is doing; the children inherit this
    while True:
        res = _one_round(a, out)
        if res["parsed"] or res["failed"]:
            print(res, flush=True)
        if not a.watch:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
