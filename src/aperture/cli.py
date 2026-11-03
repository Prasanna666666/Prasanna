"""``aperture`` command line interface."""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import signal
import sys
import threading
from datetime import date
from collections.abc import Callable, Sequence
from pathlib import Path

from .bootstrap import AppContext, ServiceUnavailableError
from .config import ENV_ONLINE, Paths, Settings, configure_environment, default_paths
from .export import run_job
from .indexing.runner import ScanOptions
from .safety import drive_problem, enable_offline_guard, resolve_export_dir, resolve_photo_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aperture", description="Private, offline AI photo agent")
    parser.add_argument("--insecure", action="store_true",
                        help="run photo commands outside the sandbox/Docker (not recommended; before the command: aperture --insecure ui)")
    sub = parser.add_subparsers(dest="command", required=True)
    doc = sub.add_parser("doctor", help="check the drive, models, Ollama and database")
    doc.add_argument("--stats", action="store_true", help="also count photos/faces/text (slow on a big library or an external disk)")
    sub.add_parser("fetch-models", help="one-off model download (the only command that uses the network)")
    scan = sub.add_parser("scan", help="index the photo folder (resumable)")
    scan.add_argument("--no-clip", action="store_true")
    scan.add_argument("--no-faces", action="store_true")
    scan.add_argument("--no-ocr", action="store_true")
    scan.add_argument("--retry-errors", action="store_true")
    scan.add_argument("--regroup-faces", action="store_true")
    deep = sub.add_parser("deepmeta", help="read and store EVERY detail the photos carry (EXIF, GPS, XMP, IPTC, colour profile, fingerprint); resumable")
    deep.add_argument("--limit", type=int, default=0, help="only this many photos (0 = all that are missing)")
    det = sub.add_parser("details", help="read and store what is IN each picture: scene and object labels, animals and people with boxes, text with boxes, landmark tags; resumable")
    det.add_argument("--limit", type=int, default=0, help="only this many photos (0 = all that are missing)")
    det.add_argument("--no-vision", action="store_true", help="skip Apple Vision (only the quick landmark and scene tags)")
    ask = sub.add_parser("ask", help="ask the agent in plain English")
    ask.add_argument("request", nargs="+")
    ask.add_argument("--limit", type=int, default=20, help="rows to print (results are never truncated internally)")
    job = sub.add_parser("export-job", help="run a queued export job (used by the UI)")
    job.add_argument("job_id")
    sub.add_parser("stats", help="print library statistics")
    sub.add_parser("eval-plans", help="measure how accurately the local LLM turns requests into plans (no photos needed)")
    sub.add_parser("check", help="measure every step of a search and a chat on this Mac (seconds) plus the routing accuracy: one command, all the numbers")
    sub.add_parser("eval-tools", help="measure the tool-using agent over ALL plan and routing test cases (about 2 minutes)")
    sub.add_parser("eval-routes", help="measure how well the AI tells photo requests from ordinary conversation (fast, no photos needed)")
    ev = sub.add_parser("eval", help="measure search precision/recall against your own golden set")
    ev.add_argument("golden", nargs="?", help="JSON file of requests and the files that truly match")
    ev.add_argument("--template", metavar="FILE", help="write a starter golden file and exit")
    ev.add_argument("--sweep", action="store_true", help="try every visual strictness and recommend one")
    ev.add_argument("--target", type=float, default=0.9)
    cfg = sub.add_parser("settings", help="show or change settings")
    cfg.add_argument("--photo-dir")
    cfg.add_argument("--export-dir")
    cfg.add_argument("--ollama-model")
    sec = sub.add_parser("secure-ui", help="serve the web UI inside the macOS sandbox (no internet, photos read-only) - the normal way")
    sec.add_argument("--port", type=int, default=None, help="default: the first free port from 8765 (an explicit port must be free)")
    sec.add_argument("--classic", action="store_true", help="start the older Streamlit screens (Photos, People, Tidy up, Settings) instead of the fast web app")
    sec.add_argument("--no-browser", action="store_true", help="do not open the page in your browser when it is ready")
    sec.add_argument("--allow-moves", action="store_true", help="let Tidy up move files inside the photo folder (off in the sandbox by default)")
    web = sub.add_parser("web", help="serve Lumo's fast web app on 127.0.0.1 (needs the sandbox/Docker, or --insecure)")
    web.add_argument("--port", type=int, default=8765)
    ui = sub.add_parser("ui", help="serve the web UI on 127.0.0.1 (needs the sandbox/Docker, or --insecure)")
    ui.add_argument("--port", type=int, default=8765)
    app = sub.add_parser("app", help="open Aperture in its own window")
    app.add_argument("--port", type=int, default=8765)
    install = sub.add_parser("install-launcher", help="create Aperture.app in ~/Applications")
    install.add_argument("--dest")
    cap = sub.add_parser("caption", help="describe every photo with the vision model, in the background (slow, resumable)")
    cap.add_argument("--limit", type=int, default=0)
    sub.add_parser("bench", help="time the app's pages on this machine and show where time goes")
    sub.add_parser("install-service", help="keep Lumo running in the background; prints the address to bookmark")
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


def cmd_doctor(ctx: AppContext, with_stats: bool = False) -> int:
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
    if with_stats:
        print(json.dumps(_stats(conn), indent=2))
    else:
        print("(library counts skipped: they can take minutes on a big library; run `aperture doctor --stats` to include them)")
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
    from .agent.loop import LoopPlanner
    from .agent.planner import Planner
    from .evaluation import TARGET, evaluate_plans

    planner = LoopPlanner(ctx.llm()) if ctx.settings.agentic else Planner(ctx.llm())
    result = evaluate_plans(planner, on_case=lambda n, t: print(f"\r{n}/{t}", end="", flush=True))
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
    if stop.is_set():  # stopped on purpose: the next run continues
        return 0
    return index_everything_else(ctx, stop)


def index_everything_else(ctx: AppContext, stop: threading.Event) -> int:
    """After the photos are indexed: read every remaining detail (full metadata, what is in each picture, flags, trips, duplicates)."""
    from .indexing import derive

    print("reading the full metadata of every photo ...", flush=True)
    cmd_deepmeta(ctx, argparse.Namespace(limit=0))
    if stop.is_set():
        return 0
    print("reading what is in every picture ...", flush=True)
    cmd_details(ctx, argparse.Namespace(limit=0, no_vision=False))
    if stop.is_set():
        return 0
    embedder = ctx.search_embedder()
    if embedder is not None and not stop.is_set():
        from .indexing import faceattrs

        print("reading expression and age group of every face ...", flush=True)
        conn = ctx.db.connect()
        try:
            conn.execute("DELETE FROM photo_labels WHERE source='face'")
            print(f"  {faceattrs.run(conn, ctx.paths.data, embedder, stop=stop):,} faces")
        finally:
            conn.close()
    conn = ctx.db.connect()
    try:
        print(f"capture flags: {derive.derive_meta_labels(conn):,}; trips and events: {derive.build_events(conn):,}")
    finally:
        conn.close()
    return 0


def cmd_deepmeta(ctx: AppContext, args: argparse.Namespace) -> int:
    from .indexing import deepmeta

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        os.nice(10)
    except OSError:
        pass
    conn = ctx.db.connect()
    try:
        total = len(deepmeta.pending(conn, args.limit))
        print(f"{total:,} photos to read" + (" (exiftool found: maker notes included)" if shutil.which("exiftool") else " (install exiftool for maker notes: brew install exiftool)"))
        done, failed = deepmeta.run(conn, args.limit, stop, lambda n, t: print(f"  {n:,} / {t:,}", flush=True))
    finally:
        conn.close()
    print(f"deepmeta: {done:,} stored, {failed:,} unreadable")
    return 0


def cmd_details(ctx: AppContext, args: argparse.Namespace) -> int:
    from .indexing import details
    from .ml.vision_details import VisionDetails, vision_available

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    try:
        os.nice(10)
    except OSError:
        pass
    conn = ctx.db.connect()
    try:
        embedder = ctx.search_embedder()
        if embedder is not None:
            print("landmark and scene tags from the stored image embeddings ...", flush=True)
            print(f"  {details.clip_tags(conn, ctx.embedding_index(), embedder):,} tags")
        if args.no_vision:
            return 0
        if not vision_available():
            print("Apple Vision is not available here (needs macOS with pyobjc-framework-Vision); skipped objects, labels and text boxes.")
            return 0
        total = len(details.pending(conn, args.limit))
        print(f"{total:,} pictures to read", flush=True)
        done, bad = details.run(conn, ctx.paths.data, VisionDetails(), args.limit, stop, lambda n, t: print(f"  {n:,} / {t:,}", flush=True))
        print(f"details: {done:,} stored, {bad:,} unreadable")
    finally:
        conn.close()
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


def cmd_caption(paths: Paths, limit: int) -> int:
    from .agent.captions import caption_all
    from .agent.llm import OllamaVision

    if _require_drive(paths):
        return 2
    _setup_logging(paths)
    ctx = AppContext(paths)
    os.nice(15)  # never get in the way of searching
    conn = ctx.db.connect()
    vision = OllamaVision(ctx.settings.ollama_url, ctx.settings.vision_model, timeout=180.0, keep_alive="2m")
    described, failed = caption_all(
        conn, paths, vision, ctx.settings.vision_model, limit=limit,
        progress=lambda done, total: print(f"\rdescribed {done}/{total}", end="", flush=True),
    )  # fmt: skip
    print(f"\nDone: {described} described, {failed} failed.")
    return 0 if described or not failed else 1


# Commands that open your photos or serve the UI: they must run inside the sandbox or Docker (APERTURE_SANDBOXED=1).
GUARDED = {"ui", "web", "app", "scan", "deepmeta", "details", "ask", "caption", "export-job", "install-service", "install-launcher"}
REFUSAL = (
    "Refusing to run outside the secure environment (no internet, photos read-only).\n"
    "  Normal way:    aperture secure-ui          (macOS sandbox)\n"
    "  Or Docker:     docker compose -f docker-compose.aperture.yml up -d\n"
    "  Override:      aperture --insecure {cmd}   (not recommended)"
)


def secure_environment() -> bool:
    return os.environ.get("APERTURE_SANDBOXED") == "1"


def port_is_free(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def first_free_port(start: int = 8765, tries: int = 25) -> int | None:
    return next((p for p in range(start, start + tries) if port_is_free(p)), None)


def listener_pid(port: int) -> int | None:
    """PID of the process listening on 127.0.0.1:port (None if nobody)."""
    import subprocess

    try:
        out = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    pids = [int(x) for x in out.split() if x.isdigit()]
    return pids[0] if pids else None


def command_of(pid: int) -> str:
    import subprocess

    try:
        return subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def is_aperture_ui(command: str) -> bool:
    """True only for Aperture's own web server (never another program that happens to use the port)."""
    c = command.lower()
    if "aperture" not in c or "scan" in c.split() or "caption" in c.split():
        return False
    return ("-m aperture ui" in c or "aperture ui" in c or "-m aperture web" in c or "aperture web" in c
            or "aperture/ui/app.py" in c or "aperture-sandboxed" in c)


def stop_process(pid: int, wait: float = 8.0) -> bool:
    """Ask a process to stop (SIGTERM), then force it if it ignores us. True once it is gone."""
    import time

    try:
        os.kill(pid, signal.SIGCONT)  # a copy suspended with Ctrl+Z ignores SIGTERM until it is allowed to run again
    except OSError:
        pass
    for sig, limit in ((signal.SIGTERM, wait), (signal.SIGKILL, 3.0)):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return True
        except OSError:
            return False
        deadline = time.monotonic() + limit
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return True
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)
    return False


def stop_old_ui(pid_file: Path, port: int) -> list[str]:
    """Stop an older Aperture web server: the one a previous `secure-ui` recorded, and any Aperture UI on `port`."""
    said: list[str] = []
    candidates: list[int] = []
    try:
        candidates.append(int(pid_file.read_text().strip()))
    except (OSError, ValueError):
        pass
    on_port = listener_pid(port)
    if on_port is not None and on_port not in candidates:
        candidates.append(on_port)
    for pid in candidates:
        if pid != os.getpid() and is_aperture_ui(command_of(pid)):
            said.append(f"Stopped the older Aperture on port {port} (process {pid})." if stop_process(pid)
                        else f"Could not stop the older Aperture (process {pid}).")
    pid_file.unlink(missing_ok=True)
    return said


def open_when_ready(port: int, attempts: int = 90, health: str = "/api/health") -> None:
    """Open the page in the default browser as soon as the server answers (runs in a background thread)."""
    import time
    import urllib.request
    import webbrowser

    for _ in range(attempts):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{health}", timeout=1):  # noqa: S310 - loopback
                webbrowser.open(f"http://127.0.0.1:{port}")
                return
        except OSError:
            time.sleep(1)


def cmd_secure_ui(paths: Paths, args: argparse.Namespace) -> int:
    """Start the UI under scripts/aperture-sandboxed.sh using the photo/export folders from the saved settings."""
    import subprocess

    if sys.platform != "darwin":
        print("secure-ui needs macOS (sandbox-exec). On other systems use Docker: docker-compose.aperture.yml")
        return 2
    script = Path(__file__).resolve().parents[2] / "scripts" / "aperture-sandboxed.sh"
    if not script.exists():
        print(f"Cannot find {script}. Run this from a git checkout of Aperture (pip install -e .).")
        return 2
    if _require_drive(paths):
        return 2
    settings = Settings.load(paths)
    photo = Path(settings.photo_dir).expanduser()
    if not photo.is_dir():
        print(f"Photo folder not found: {photo}\nSet the right one with:  aperture settings --photo-dir /path/to/photos")
        return 2
    pid_file = paths.data / "ui.pid"
    wanted = args.port if args.port is not None else 8765
    for line in stop_old_ui(pid_file, wanted):
        print(line)
    if args.port is not None:
        port = args.port
        if not port_is_free(port):
            print(f"Port {port} is in use by another program, not Aperture. Leave out --port and I will pick a free one.")
            return 2
    else:
        port = wanted if port_is_free(wanted) else first_free_port(wanted)
        if port is None:
            print("No free port found near 8765. Close some programs and try again.")
            return 2
        if port != wanted:
            print(f"Port {wanted} is used by another program, so I am using {port}.")
    cmd = [str(script), str(photo)]
    export = Path(settings.export_dir).expanduser() if settings.export_dir else None
    if export is not None and export.is_dir():
        cmd.append(str(export))
    cmd += ["--", sys.executable, "-m", "aperture", "ui" if args.classic else "web", "--port", str(port)]
    env = dict(os.environ, ALLOW_MOVES="yes" if args.allow_moves else "no", AP_ROOT=str(paths.root))
    print(f"Starting Aperture in the sandbox on http://127.0.0.1:{port}  (photos: read-only"
          f"{', moves allowed' if args.allow_moves else ''}; no internet). Press Ctrl+C to stop.")
    if not args.no_browser:
        health = "/_stcore/health" if args.classic else "/api/health"
        threading.Thread(target=open_when_ready, args=(port, 90, health), daemon=True).start()
    proc = subprocess.Popen(cmd, env=env)  # noqa: S603
    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text(str(proc.pid))
    except OSError:
        pass  # not being able to remember it only means the next start cannot stop this one automatically
    try:
        return int(proc.wait() or 0)
    except KeyboardInterrupt:
        stop_process(proc.pid)
        return 0
    finally:
        pid_file.unlink(missing_ok=True)


def time_steps(steps: list[tuple[str, Callable[[], object]]]) -> list[tuple[str, float, str]]:
    """Run each step once and time it. A failing step is reported, not raised."""
    import time

    rows = []
    for label, fn in steps:
        started = time.perf_counter()
        try:
            fn()
            error = ""
        except Exception as exc:
            error = f"FAILED: {exc}"[:120]
        rows.append((label, time.perf_counter() - started, error))
    return rows


# What each step should take on an 8 GB M1 for the app to feel responsive (seconds).
BUDGET = {"router": 1.5, "first words": 3.0, "AI plan": 6.0, "instant photo matches": 0.5}


def cmd_check(ctx: AppContext) -> int:
    from .agent.planner import Planner, PlannerContext
    from .evaluation import evaluate_routes
    from .search.quick import quick_ids

    llm, router = ctx.llm(), ctx.router()
    conn = ctx.db.connect()

    def first_words() -> None:
        next(iter(llm.stream_chat("Reply briefly.", [{"role": "user", "content": "Tell me a joke."}], max_tokens=40)))

    steps = [
        ("AI model load (cold start)", llm.warm),
        ("router: photos or chat?", lambda: router("tell me a joke", False)),
        ("chat: first words appear", first_words),
        ("photo search: the AI plan", lambda: Planner(llm).plan("sunset photos", PlannerContext(today=date.today()))),
        ("image-search model load", ctx.search_embedder),
        ("instant photo matches", lambda: quick_ids(conn, "sunset", ctx.embedding_index, ctx.search_embedder, ctx.settings.visual_strictness)),
    ]
    print(f"model: {ctx.settings.ollama_model}\n")
    for label, seconds, error in time_steps(steps):
        key = next((k for k in BUDGET if k in label), None)
        flag = "  <- slow" if key and seconds > BUDGET[key] else ""
        print(f"{seconds:7.2f}s  {label}{flag}  {error}".rstrip())
    conn.close()
    cases = json.loads((Path(__file__).parent / "eval_data" / "route_cases.json").read_text())
    correct, wrong, slower = evaluate_routes(router, cases)
    print(f"\nrouting accuracy: {correct / len(cases):.0%} ({correct}/{len(cases)}); {len(slower)} simple searches took the slower route")
    for line in wrong[:8]:
        print("  x", line)
    return 0


def cmd_eval_tools(ctx: AppContext) -> int:
    import time

    from .agent.toolagent import ToolAgent
    from .evaluation import evaluate_tool_agent, load_plan_cases

    import numpy as np

    seconds: list[float] = []

    class Found(Exception):  # raised at the first real search: we only measure WHAT the agent decided to search for
        def __init__(self, call: dict) -> None:
            self.call = call

    class Recording(ToolAgent):
        def _execute(self, call, request, previous_ids, history, timings, shown=None):
            if call["name"] in ("find_photos", "count_photos", "copy_photos"):
                raise Found(call)
            return super()._execute(call, request, previous_ids, history, timings, shown)

    def decide(request: str, previous: bool, people: list[str]):
        """Runs the REAL loop (look-ups and overviews included) with stand-in tools, up to the first search."""
        def lookup(kind: str, text: str) -> list[str]:
            return [p for p in people if text.lower() in p.lower()] if kind == "person" else [text.title()]

        facts = ("LIBRARY SIZE: 10,000 files, 10,000 indexed\nPHOTOS SPAN: 2014-03-02 to 2026-10-30\n"
                 "PLACES IN THIS LIBRARY: Goa, India; Paris, France; Japan; Eindhoven, Netherlands; Amsterdam, Netherlands; Switzerland"
                 + (("\nPEOPLE FOUND: " + ", ".join(people)) if people else ""))  # the same kind of facts the real app retrieves
        agent = Recording(ctx.llm(), None, lambda r: facts,
                          overview=lambda prev: "LIBRARY FACTS: 10,000 files, all indexed", lookup=lookup)
        started = time.perf_counter()
        try:
            reply = agent.ask(request, np.array([1]) if previous else None)
        except Found as found:
            seconds.append(time.perf_counter() - started)
            return "tool", found.call["name"], found.call["arguments"]
        seconds.append(time.perf_counter() - started)
        words = ""
        if reply.stream is not None:
            words = "".join(list(reply.stream)[:3])
        return "words", words or reply.text, {}

    routes = json.loads((Path(__file__).parent / "eval_data" / "route_cases.json").read_text())
    result = evaluate_tool_agent(decide, load_plan_cases(), routes)
    print(f"tool agent with {ctx.settings.ollama_model}")
    print(f"  right tool and right arguments: {result.plan_correct / result.plan_total:.0%} ({result.plan_correct}/{result.plan_total})")
    print(f"  tool-or-words decision:         {result.route_correct / result.route_total:.0%} ({result.route_correct}/{result.route_total})")
    print(f"  average time to decide:         {sum(seconds) / max(len(seconds), 1):.1f}s (the whole loop, up to the first search)")
    print("\nwrong plans:")
    for request, problems in result.failures[:10]:
        print(f"  x {request!r}: {'; '.join(problems)}")
    print("\nwrong tool-or-words:")
    for request, problems in result.route_failures[:10]:
        print(f"  x {request!r}: {'; '.join(problems)}")
    return 0


def cmd_eval_routes(ctx: AppContext) -> int:
    from .evaluation import evaluate_routes

    cases = json.loads((Path(__file__).parent / "eval_data" / "route_cases.json").read_text())
    correct, wrong, slower = evaluate_routes(ctx.router(), cases)
    print(f"route accuracy with {ctx.settings.ollama_model}: {correct / len(cases):.0%} ({correct}/{len(cases)})")
    for line in wrong:
        print("  x", line)
    for line in slower:
        print("  ~", line)
    return 0 if correct / len(cases) >= 0.9 else 1


def cmd_bench(paths: Paths) -> int:
    """Time a cold render of the app, the database and the drive; print the slowest steps."""
    import cProfile
    import pstats
    import time

    from streamlit.testing.v1 import AppTest

    from . import launcher
    from .db import Database

    if _require_drive(paths):
        return 2
    t = time.perf_counter()
    conn = Database(paths.db).connect()
    n = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    conn.execute("SELECT COUNT(DISTINCT place) FROM items").fetchone()
    print(f"database: {n:,} items, opened and queried in {time.perf_counter() - t:.2f}s")
    t = time.perf_counter()
    test = AppTest.from_file(str(launcher.ui_script()), default_timeout=300)
    profiler = cProfile.Profile()
    profiler.enable()
    test.run()
    profiler.disable()
    print(f"first page render: {time.perf_counter() - t:.2f}s ({len(test.exception)} errors)")
    stats = pstats.Stats(profiler)
    rows = sorted(stats.stats.items(), key=lambda kv: kv[1][3], reverse=True)  # type: ignore[attr-defined]
    print("slowest steps (cumulative seconds):")
    shown = 0
    for (file, line, name), (_, calls, _, cum, _) in rows:
        if "aperture" in file and "site-packages" not in file and cum > 0.05:
            print(f"  {cum:6.2f}s  {file.split('aperture/')[-1]}:{line} {name} ({calls}x)")
            shown += 1
            if shown >= 10:
                break
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = default_paths()
    if args.command in GUARDED and not (args.insecure or secure_environment()):
        print(REFUSAL.format(cmd=args.command))
        return 2
    online = args.command == "fetch-models"
    if online and os.environ.get("APERTURE_NEVER_ONLINE") == "1":
        print("Network access is permanently disabled here (APERTURE_NEVER_ONLINE=1). Fetch models with a normal install "
              "outside the container/sandbox, then reuse the Aperture/models folder.")
        return 2
    if online:
        os.environ[ENV_ONLINE] = "1"
    configure_environment(paths, online=online)
    enable_offline_guard()  # no-op while fetching models

    if args.command == "secure-ui":
        return cmd_secure_ui(paths, args)
    if args.command in ("app", "ui", "install-launcher", "install-service"):
        from . import launcher

        if args.command == "ui":
            return launcher.run_ui(args.port)
        if _require_drive(paths):
            return 2
        if args.command == "install-service":
            url = launcher.install_service(paths)
            print(
                f"Lumo is running in the background and starts at every login.\nOpen: {url}\n(also works: http://127.0.0.1:8765)"
            )
            return 0
        if args.command == "app":
            return launcher.run_window(args.port)
        print(launcher.install_app_bundle(paths, None if not args.dest else __import__("pathlib").Path(args.dest)))
        return 0

    if args.command == "bench":
        return cmd_bench(paths)
    if args.command == "caption":
        return cmd_caption(paths, args.limit)

    if _require_drive(paths):
        return 2
    _setup_logging(paths)
    ctx = AppContext(paths)
    if args.command == "fetch-models":
        from .ml.fetch import fetch_all

        fetch_all(paths, ctx.settings)
        return 0
    if args.command == "doctor":
        return cmd_doctor(ctx, args.stats)
    if args.command == "scan":
        return cmd_scan(ctx, args)
    if args.command == "details":
        return cmd_details(ctx, args)
    if args.command == "deepmeta":
        return cmd_deepmeta(ctx, args)
    if args.command == "ask":
        return cmd_ask(ctx, args)
    if args.command == "web":
        from .web.server import serve

        return serve(ctx, args.port)
    if args.command == "eval-plans":
        return cmd_eval_plans(ctx)
    if args.command == "eval-routes":
        return cmd_eval_routes(ctx)
    if args.command == "check":
        return cmd_check(ctx)
    if args.command == "eval-tools":
        return cmd_eval_tools(ctx)
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
