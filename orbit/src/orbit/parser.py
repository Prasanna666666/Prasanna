"""The isolated parser: turns untrusted files (PDF, CSV, text) into plain JSON. It is the only code that opens them.

Runs in its own container with NO network, the inbox mounted read-only, and a single writable output folder that the
app mounts read-only. Each file is parsed in a throw-away subprocess with CPU, memory and time limits, so a hostile or
broken file can at worst fail that one file. Output is JSON only (never pickle), text capped and stripped of control
characters; the app still treats it as untrusted data.

    orbit-parser --once  [--inbox /inbox --out /parsed]
    orbit-parser --watch
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
MAX_BYTES = 50 * 1024 * 1024
MAX_TEXT = 2_000_000
MAX_PAGES = 500
MAX_CSV_ROWS = 200_000
MAX_DATA_ROWS = 50_000  # structured rows/lines kept for statements
MAX_CELL = 300
TIMEOUT_S = 60
KINDS = {".txt": "text", ".md": "text", ".csv": "csv", ".tsv": "csv", ".pdf": "pdf", ".mt940": "text", ".sta": "text", ".xml": "text"}
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str) -> str:
    return _CTRL.sub("", text)[:MAX_TEXT]


def extract(path: Path) -> dict:
    """In-process extraction. Called only inside the limited subprocess (or by tests)."""
    kind = KINDS.get(path.suffix.lower())
    meta: dict = {}
    data: dict = {}
    if kind == "text":
        text = path.read_text(encoding="utf-8", errors="replace")
    elif kind == "csv":
        head = path.read_bytes()[:4096].decode("utf-8", "replace")
        delimiter = max((",", ";", "\t"), key=head.split("\n")[0].count)  # Dutch banks export with ; or tab
        with path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
            rows = []
            for i, row in enumerate(csv.reader(f, delimiter=delimiter)):
                if i >= MAX_CSV_ROWS:
                    meta["truncated"] = True
                    break
                rows.append(row)
        meta["rows"] = len(rows)
        meta["columns"] = [clean(c)[:80] for c in rows[0]][:50] if rows else []
        text = "\n".join(" | ".join(r) for r in rows)
        data["rows"] = [[clean(c)[:MAX_CELL] for c in r][:60] for r in rows[:MAX_DATA_ROWS]]  # exact cells, for statements
    elif kind == "pdf":
        import pymupdf  # only installed in the parser image

        with pymupdf.open(path) as doc:
            meta["pages"] = doc.page_count
            text = "\n\n".join(doc[i].get_text() for i in range(min(doc.page_count, MAX_PAGES)))
            lines: list[str] = []
            for i in range(min(doc.page_count, MAX_PAGES)):
                lines += _visual_lines(doc[i].get_text("words"))
            data["lines"] = [clean(x)[:600] for x in lines[:MAX_DATA_ROWS]]
            table: list = []
            for i in range(min(doc.page_count, MAX_PAGES)):
                table += _table_lines(doc[i].get_text("words"))
            data["table"] = table[:MAX_DATA_ROWS]  # every line as cells with their horizontal position: columns can be recovered exactly
            if doc.page_count > MAX_PAGES:
                meta["truncated"] = True
    else:
        raise ValueError(f"unsupported file type: {path.suffix}")
    if kind == "text":
        data["lines"] = [clean(x)[:600] for x in text.splitlines()[:MAX_DATA_ROWS]]
        rows = _delimited_rows(text)  # a plain tab- or semicolon-separated export (some banks give these with no header row)
        if rows:
            data["rows"] = rows
    return {"kind": kind, "text": clean(text), "meta": meta, "data": data}


def _delimited_rows(text: str) -> list[list[str]]:
    """Rows of a plain delimited text file, or [] if it does not look like one (the first lines must split into the same number of columns)."""
    head = [ln for ln in text.splitlines()[:8] if ln.strip()]
    if len(head) < 2:
        return []
    for delimiter in ("\t", ";", ","):
        counts = {ln.count(delimiter) for ln in head[:5]}
        if len(counts) == 1 and counts != {0} and next(iter(counts)) >= 2:
            reader = csv.reader(text.splitlines(), delimiter=delimiter)
            return [[clean(c)[:MAX_CELL] for c in r][:60] for _, r in zip(range(MAX_DATA_ROWS), reader)]
    return []


def _table_lines(words: list, gap: float = 7.0) -> list[list[list]]:
    """Lines as cells: [[x0, x1, text], ...]. Words on one line that are closer than `gap` points belong to one cell; a wider gap starts a new cell."""
    items = sorted(((round((w[1] + w[3]) / 2), w[0], w[2], clean(str(w[4]))) for w in words if str(w[4]).strip()), key=lambda t: (t[0], t[1]))
    lines: list[list[tuple[float, float, str]]] = []
    last_y = None
    for y, x0, x1, text in items:
        if last_y is None or abs(y - last_y) > 3:
            lines.append([])
            last_y = y
        lines[-1].append((x0, x1, text))
    out = []
    for line in lines:
        line.sort()
        cells: list[list] = []
        for x0, x1, text in line:
            if cells and x0 - cells[-1][1] < gap:
                cells[-1][1], cells[-1][2] = max(cells[-1][1], x1), cells[-1][2] + " " + text
            else:
                cells.append([round(x0, 1), round(x1, 1), text])
        out.append([[c[0], c[1], c[2][:200]] for c in cells])
    return out


def _visual_lines(words: list) -> list[str]:
    """Rebuild the lines of a page as they look: words with nearly the same height are one line, in left-to-right order.
    A statement table is then 'date  description  amount  balance' on one line, however the PDF stores its cells."""
    items = sorted(((round((w[1] + w[3]) / 2), w[0], w[2], str(w[4])) for w in words), key=lambda t: (t[0], t[1]))
    lines: list[list[tuple[float, float, str]]] = []
    last_y = None
    for y, x0, x1, text in items:
        if last_y is None or abs(y - last_y) > 3:
            lines.append([])
            last_y = y
        lines[-1].append((x0, x1, text))
    out = []
    for line in lines:
        line.sort()
        out.append(" ".join(t for _, _, t in line))
    return out


def _limits() -> None:  # runs in the child before exec (Linux/macOS)
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_S, TIMEOUT_S))
    resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def extract_isolated(path: Path, timeout: int = TIMEOUT_S) -> dict:
    r = subprocess.run([sys.executable, "-I", "-m", "orbit.parser", "--extract-one", str(path)],
                       capture_output=True, timeout=timeout, preexec_fn=_limits, check=False)  # noqa: PLW1509
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[-300:] or f"parser exited {r.returncode}")
    return json.loads(r.stdout)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def process_inbox(inbox: Path, out: Path, isolated: bool = True, area: str = "") -> dict[str, int]:
    """Parse every new supported file under inbox into out/<sha256>.json. Same content is never parsed twice."""
    out.mkdir(parents=True, exist_ok=True)
    root = inbox.resolve()
    done = skipped = failed = 0
    for f in sorted(root.rglob("*")):
        if not f.is_file() or f.is_symlink() or root not in f.resolve().parents:
            continue
        if f.suffix.lower() not in KINDS or f.stat().st_size > MAX_BYTES:
            skipped += 1
            continue
        digest = sha256(f)
        if area:
            digest = hashlib.sha256((area + digest).encode()).hexdigest()  # the same file in two folders is two documents
        target = out / f"{digest}.json"
        if target.exists():
            continue
        try:
            res = extract_isolated(f) if isolated else extract(f)
        except Exception as e:
            print(f"FAILED {f.name}: {e}", file=sys.stderr, flush=True)
            failed += 1
            continue
        doc = {"schema": SCHEMA, "sha256": digest, "name": clean(f.name)[:255], "bytes": f.stat().st_size,
               "parsed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **({"area": area} if area else {}), **res}
        tmp = out / f".{digest}.tmp"
        tmp.write_text(json.dumps(doc, ensure_ascii=False))
        os.replace(tmp, target)  # atomic: the app never sees a half-written file
        done += 1
    return {"parsed": done, "skipped": skipped, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="orbit-parser")
    ap.add_argument("--inbox", default=os.environ.get("ORBIT_INBOX", str(Path.home() / "OrbitInbox")))
    ap.add_argument("--out", default=os.environ.get("ORBIT_PARSED", str(Path.home() / "OrbitParsed")))
    ap.add_argument("--finance", default=os.environ.get("ORBIT_FINANCE", ""), help="folder of bank statements and finance files (read-only)")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--extract-one", metavar="FILE", help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.extract_one:
        sys.stdout.write(json.dumps(extract(Path(a.extract_one)), ensure_ascii=False))
        return 0
    while True:
        res = process_inbox(Path(a.inbox), Path(a.out))
        if a.finance and Path(a.finance).is_dir():
            fin = process_inbox(Path(a.finance), Path(a.out), area="finance")
            res = {k: res[k] + fin[k] for k in res}
        if res["parsed"] or res["failed"]:
            print(res, flush=True)
        if not a.watch:
            return 0
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
