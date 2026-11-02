"""``aperture`` command line interface."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
from collections.abc import Sequence
from pathlib import Path

from .bootstrap import AppContext, ServiceUnavailableError
from .config import ENV_ONLINE, Paths, Settings, configure_environment, default_paths
from .export import run_job
from .indexing.runner import ScanOptions
from .safety import drive_problem, enable_offline_guard, resolve_export_dir, resolve_photo_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aperture", description="Private, offline AI photo agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="check the drive, models, Ollama and database")
    sub.add_parser("fetch-models", help="one-off model download (the only command that uses the network)")
    scan = sub.add_parser("scan", help="index the photo folder (resumable)")
    scan.add_argument("--no-clip", action="store_true")
    scan.add_argument("--no-faces", action="store_true")
    scan.add_argument("--no-ocr", action="store_true")
    scan.add_argument("--retry-errors", action="store_true")
    scan.add_argument("--regroup-faces", action="store_true")
    ask = sub.add_parser("ask", help="ask the agent in plain English")
    ask.add_argument("request", nargs="+")
    ask.add_argument("--limit", type=int, default=20, help="rows to print (results are never truncated internally)")
    job = sub.add_parser("export-job", help="run a queued export job (used by the UI)")
    job.add_argument("job_id")
    sub.add_parser("stats", help="print library statistics")
    sub.add_parser("eval-plans", help="measure how accurately the local LLM turns requests into plans (no photos needed)")
    ev = sub.add_parser("eval", help="measure search precision/recall against your own golden set")
    ev.add_argument("golden", nargs="?", help="JSON file of requests and the files that truly match")
    ev.add_argument("--template", metavar="FILE", help="write a starter golden file and exit")
    ev.add_argument("--sweep", action="store_true", help="try every visual strictness and recommend one")
    ev.add_argument("--target", type=float, default=0.9)
    cfg = sub.add_parser("settings", help="show or change settings")
    cfg.add_argument("--photo-dir")
    cfg.add_argument("--export-dir")
    cfg.add_argument("--ollama-model")
    ui = sub.add_parser("ui", help="serve the web UI on 127.0.0.1")
    ui.add_argument("--port", type=int, default=8765)
    app = sub.add_parser("app", help="open Aperture in its own window")
    app.add_argument("--port", type=int, default=8765)
    install = sub.add_parser("install-launcher", help="create Aperture.app in ~/Applications")
    install.add_argument("--dest")
    return parser


def _require_drive(paths: Paths) -> int:
    problem = drive_problem(paths.drive)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2
    paths.ensure()
    return 0


def _setup_logging(paths: Paths) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if paths.logs.is_dir():
        handlers.append(logging.FileHandler(paths.logs / "aperture.log"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers)


def cmd_doctor(ctx: AppContext) -> int:
    ok = True

    def line(good: bool, label: str, detail: str = "") -> None:
        nonlocal ok
        ok &= good
        print(f"[{'OK' if good else 'FAIL'}] {label} {detail}".rstrip())

    s, p = ctx.settings, ctx.paths
    line(True, "external drive", str(p.drive))
    try:
        resolve_photo_dir(p, s.photo_dir)
        line(os.path.isdir(s.photo_dir), "photo folder", s.photo_dir)
        resolve_export_dir(p, s.export_dir, s.photo_dir)
        line(True, "export folder", s.export_dir)
    except PermissionError as exc:
        line(False, "folders", str(exc))
    line(all((p.face_models / f).exists() for f in ("det_10g.onnx", "w600k_r50.onnx")), "face models", str(p.face_models))
    line((p.geo / "cities15000.txt").exists(), "place data (GeoNames)", "optional")
    from .ml.ocr import vision_available

    line(vision_available(), "Apple Vision OCR", "macOS only")
    try:
        ctx.build_embedder().close()
        line(True, "CLIP model", f"{s.clip_model}/{s.clip_pretrained}")
    except ServiceUnavailableError as exc:
        line(False, "CLIP model", str(exc))
    healthy, detail = ctx.llm().health()
    line(healthy, "Ollama", detail)
    conn = ctx.db.connect()
    line(True, "database", str(p.db))
    print(json.dumps(_stats(conn), indent=2))
    return 0 if ok else 1


def _stats(conn) -> dict[str, int]:  # type: ignore[no-untyped-def]
    q = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
    return {
        "photos": q("SELECT COUNT(*) FROM items WHERE missing=0"),
        "indexed": q("SELECT COUNT(*) FROM items WHERE missing=0 AND meta_done=1"),
        "embedded": q("SELECT COUNT(*) FROM embeddings"),
        "faces": q("SELECT COUNT(*) FROM faces"),
        "people": q("SELECT COUNT(*) FROM people WHERE hidden=0"),
        "with_text": q("SELECT COUNT(*) FROM items WHERE ocr_chars>0"),
        "errors": q("SELECT COUNT(*) FROM items WHERE error IS NOT NULL"),
    }


def cmd_eval_plans(ctx: AppContext) -> int:
    from .agent.planner import Planner
    from .evaluation import TARGET, evaluate_plans

    result = evaluate_plans(Planner(ctx.llm()), on_case=lambda n, t: print(f"\r{n}/{t}", end="", flush=True))
    print(f"\nplan accuracy with {ctx.settings.ollama_model}: {result.accuracy:.0%} ({result.correct}/{result.total})")
    for request, problems in result.failures:
        print(f"  x {request!r}: {'; '.join(problems)}")
    return 0 if result.accuracy >= TARGET else 1


def cmd_eval(ctx: AppContext, args: argparse.Namespace) -> int:
    from .evaluation import GOLDEN_TEMPLATE, evaluate_retrieval
    from .search.visual import STRICTNESS

    if args.template:
        Path(args.template).write_text(json.dumps(GOLDEN_TEMPLATE, indent=2))
        print(
            f"wrote {args.template}: list your own requests and the files that truly match, then run `aperture eval {args.template}`"
        )
        return 0
    if not args.golden:
        print("error: give a golden file (or --template FILE to create one)", file=sys.stderr)
        return 2
    golden = json.loads(Path(args.golden).read_text())
    photo = Path(ctx.settings.photo_dir)

    def ask(request: str) -> list[str]:
        reply = ctx.agent().ask(request)
        conn = ctx.db.connect()
        try:
            from .library import items_by_ids

            found = items_by_ids(conn, reply.ids.tolist())
        finally:
            conn.close()
        return [os.path.relpath(i.path, photo) for i in found.values()]

    best: tuple[str, float, float] | None = None
    for level in list(STRICTNESS) if args.sweep else [ctx.settings.visual_strictness]:
        ctx.settings.visual_strictness = level
        result = evaluate_retrieval(ask, golden)
        print(f"{level:>9}: precision {result.precision:.0%}  recall {result.recall:.0%}  ({len(result.cases)} requests)")
        if result.precision >= args.target and (best is None or result.recall > best[2]):
            best = (level, result.precision, result.recall)
        if not args.sweep:
            for c in result.cases:
                if c.precision < 1 or c.recall < 1:
                    print(f"  {c.request!r}: returned {c.returned}, relevant {c.relevant}, correct {c.true_positive}")
    if args.sweep:
        print(f"recommended strictness: {best[0]}" if best else f"no strictness reached {args.target:.0%} precision on your set")
    return 0 if (best or not args.sweep) else 1


def cmd_scan(ctx: AppContext, args: argparse.Namespace) -> int:
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        os.nice(10)  # stay polite: the UI and the LLM share this 8 GB machine
    except OSError:
        pass
    stages = ctx.settings.stages
    stages.clip &= not args.no_clip
    stages.faces &= not args.no_faces
    stages.ocr &= not args.no_ocr
    summary = ctx.scanner(stop).run(ScanOptions(args.retry_errors, 0, args.regroup_faces))
    print(f"scan {summary.state}: {summary.processed} processed, {summary.errors} errors, {summary.faces} faces")
    return 0


def cmd_ask(ctx: AppContext, args: argparse.Namespace) -> int:
    reply = ctx.agent().ask(" ".join(args.request))
    print(reply.text)
    for note in reply.notes + reply.warnings:
        print(f"  note: {note}")
    if len(reply.ids):
        conn = ctx.db.connect()
        from .models import Item

        for item_id in reply.ids[: args.limit]:
            row = conn.execute("SELECT * FROM items WHERE id=?", (int(item_id),)).fetchone()
            print("  ", Item.from_row(row).path)
        if len(reply.ids) > args.limit:
            print(f"  ... and {len(reply.ids) - args.limit:,} more (all {len(reply.ids):,} are retained)")
    return 0 if reply.kind != "error" else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = default_paths()
    online = args.command == "fetch-models"
    if online:
        os.environ[ENV_ONLINE] = "1"
    configure_environment(paths, online=online)
    enable_offline_guard()  # no-op while fetching models

    if args.command in ("app", "ui", "install-launcher"):
        from . import launcher

        if args.command == "ui":
            return launcher.run_ui(args.port)
        if _require_drive(paths):
            return 2
        if args.command == "app":
            return launcher.run_window(args.port)
        print(launcher.install_app_bundle(paths, None if not args.dest else __import__("pathlib").Path(args.dest)))
        return 0

    if _require_drive(paths):
        return 2
    _setup_logging(paths)
    ctx = AppContext(paths)
    if args.command == "fetch-models":
        from .ml.fetch import fetch_all

        fetch_all(paths, ctx.settings)
        return 0
    if args.command == "doctor":
        return cmd_doctor(ctx)
    if args.command == "scan":
        return cmd_scan(ctx, args)
    if args.command == "ask":
        return cmd_ask(ctx, args)
    if args.command == "eval-plans":
        return cmd_eval_plans(ctx)
    if args.command == "eval":
        return cmd_eval(ctx, args)
    if args.command == "export-job":
        conn = ctx.db.connect()
        report = run_job(paths, ctx.settings, conn, args.job_id)
        print(f"export done: {report.copied} copied, {report.skipped_identical} already there, {len(report.failed)} failed")
        return 0 if not report.failed else 1
    if args.command == "stats":
        print(json.dumps(_stats(ctx.db.connect()), indent=2))
        return 0
    if args.command == "settings":
        s: Settings = ctx.settings
        if args.photo_dir:
            s.photo_dir = str(resolve_photo_dir(paths, args.photo_dir))
        if args.export_dir:
            s.export_dir = str(resolve_export_dir(paths, args.export_dir, s.photo_dir))
        if args.ollama_model:
            s.ollama_model = args.ollama_model
        if args.photo_dir or args.export_dir or args.ollama_model:
            s.save(paths)
        print(json.dumps(json.loads(paths.settings_file.read_text()) if paths.settings_file.exists() else {}, indent=2))
        return 0
    return 2
