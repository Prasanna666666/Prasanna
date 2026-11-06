"""finance ui | brief | tools | tag | export-notes [dir] | import-notes [dir] | import-statements | categorise"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from kit import llm, netguard

from . import applenotes, clock, db, tagging
from .modules import ALL, tools
from .modules.today import briefing_for


def open_db():
    conn = db.connect()
    db.migrate(conn, ALL)
    return conn


# Commands that touch your database. They need the encryption key (set by the Docker deployment / scripts/up.sh),
# or an explicit ATLAS_ALLOW_PLAIN=1 for throwaway test data.
NEEDS_SECURE = {"explain-month", "ui", "brief", "tag", "import-notes", "import-statements", "categorise", "statement-report"}
REFUSAL = (
    "Refusing to open the database without encryption.\n"
    "  Normal way:   ./scripts/up.sh          (Docker: encrypted, offline, isolated)\n"
    "  Throwaway:    ATLAS_ALLOW_PLAIN=1 ATLAS_HOME=/tmp/atlas-test finance {cmd}   (fake data only)"
)


def secure_ok() -> bool:
    return bool(db.database_key()) or os.environ.get("ATLAS_ALLOW_PLAIN") == "1"


def _inbox() -> Path:
    return Path(os.environ.get("ATLAS_INBOX", Path.home() / "AtlasInbox")) / "notes"


def _model(conn, client) -> str:
    return client.resolve(db.get_setting(conn, "model", llm.DEFAULT_MODEL))


# ---- commands that need no database: never create one as a side effect ---------------------------------------------------------
def _ui(rest: list[str]) -> int:
    from . import web

    host = rest[rest.index("--host") + 1] if "--host" in rest else "127.0.0.1"
    port = int(rest[rest.index("--port") + 1]) if "--port" in rest else 8501
    return web.serve(host, port)


def _export_notes(rest: list[str]) -> int:  # a native Mac step
    out = Path(rest[0]) if rest else _inbox()
    print(applenotes.write_notes(applenotes.fetch_notes(), out), "->", out)
    return 0


def _list_tools(rest: list[str]) -> int:
    for name, t in tools(ALL).items():
        print(f"{name:20} {t.description}")
    return 0


# ---- commands that open the database ----------------------------------------------------------------------------------------
def _brief(conn, rest: list[str]) -> int:
    print(json.dumps(briefing_for(conn, clock.today()), indent=2, default=str))
    return 0


def _import_statements(conn, rest: list[str]) -> int:  # takes what the Documents service read and turns the finance files into transactions
    from . import library_client
    from .modules import money

    if library_client.base_url():
        print("Documents:", library_client.update(lambda m: print(" ", m, flush=True)) or "read")
        print(library_client.pull(conn))

    client: llm.OllamaClient | None = None
    model: str | None = None
    try:
        client = llm.OllamaClient()
        model = _model(conn, client)
    except RuntimeError as exc:
        print(f"The local model is not available ({exc}). Statements are read by the local model, so nothing was imported.")
        client = model = None
    print(money.import_statements(conn, client=client, model=model, progress=lambda m: print(" ", m, flush=True)))
    return 0


def _statement_report(conn, rest: list[str]) -> int:  # what Finance made of each finance file; shows counts only, never content
    from .modules import money

    for r in money.statement_report(conn):
        print(r)
    return 0


def _categorise(conn, rest: list[str]) -> int:  # the local model places merchants the rules could not
    from . import categorize

    client = llm.OllamaClient()
    print("updated", categorize.recategorise_with_model(conn, client, _model(conn, client)), "transactions")
    return 0


def _import_notes(conn, rest: list[str]) -> int:
    print(applenotes.import_dir(conn, Path(rest[0]) if rest else _inbox()))
    return 0


def _tag(conn, rest: list[str]) -> int:
    try:
        client = llm.OllamaClient()
        n = tagging.autotag_notes(conn, client, _model(conn, client))
    except RuntimeError:
        n = tagging.autotag_notes(conn)  # model unavailable: rules only
    print(f"tagged {n} note(s)")
    return 0


def _explain_month(conn, rest: list[str]) -> int:  # shows amounts on YOUR screen only; nothing is sent anywhere
    from . import insight

    r = insight.month_breakdown(conn, {"month": rest[0]} if rest else {})
    print(f"{r['month']}: spent {r['total']:,.2f} in {r['payments']} payments (monthly {r['monthly']:,.2f}, one-time {r['one_time']:,.2f})")
    print("\nBy file:")
    for f in r["by_file"]:
        print(f"  {f['total']:>12,.2f}  {f['payments']:>4} payments  {f['file']}")
    print("\nBiggest payments:")
    for p in r["biggest"]:
        print(f"  {p['amount']:>12,.2f}  {p['day']}  {p['category']:<12} {p['note']}" + ("  [trip/event]" if p["in_event"] else ""))
    if r["look_at"]:
        print("\nWorth a look:")
        for p in r["look_at"]:
            print(f"  {p['amount']:,.2f} on {p['day']} {p['note']}: " + "; ".join(p["why"]))
    return 0


NO_DATABASE = {"ui": _ui, "export-notes": _export_notes, "tools": _list_tools}
WITH_DATABASE = {
    "brief": _brief,
    "import-statements": _import_statements,
    "statement-report": _statement_report,
    "categorise": _categorise,
    "import-notes": _import_notes,
    "tag": _tag,
    "explain-month": _explain_month,
}


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:]) or ["ui"]
    cmd, rest = args[0], args[1:]
    if cmd in NEEDS_SECURE and not secure_ok():
        print(REFUSAL.format(cmd=cmd))
        return 2
    if cmd != "ui":
        netguard.install()
    if cmd in NO_DATABASE:
        return NO_DATABASE[cmd](rest)
    if cmd in WITH_DATABASE:
        return WITH_DATABASE[cmd](open_db(), rest)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
