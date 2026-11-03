"""orbit ui | chat | brief | tools | agents | tag | export-notes [dir] | import-notes [dir] | ingest [dir]"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import agent, agents, applenotes, db, netguard, tagging
from .modules import documents
from .modules import ALL, tools
from .modules.today import briefing_for


def open_db():
    conn = db.connect()
    db.migrate(conn, ALL)
    return conn


# Commands that touch your database. They need the encryption key (set by the Docker deployment / scripts/up.sh),
# or an explicit ORBIT_ALLOW_PLAIN=1 for throwaway test data.
NEEDS_SECURE = {"ui", "chat", "brief", "tag", "import-notes", "ingest"}
REFUSAL = (
    "Refusing to open the database without encryption.\n"
    "  Normal way:   ./scripts/up.sh          (Docker: encrypted, offline, isolated)\n"
    "  Throwaway:    ORBIT_ALLOW_PLAIN=1 ORBIT_HOME=/tmp/orbit-test orbit {cmd}   (fake data only)"
)


def secure_ok() -> bool:
    return bool(db._key()) or os.environ.get("ORBIT_ALLOW_PLAIN") == "1"


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:]) or ["ui"]
    cmd, rest = args[0], args[1:]
    if cmd in NEEDS_SECURE and not secure_ok():
        print(REFUSAL.format(cmd=cmd))
        return 2
    if cmd == "ui":
        app = Path(__file__).with_name("app.py")
        return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), *rest])
    netguard.install()
    inbox = Path(os.environ.get("ORBIT_INBOX", Path.home() / "OrbitInbox")) / "notes"
    if cmd == "export-notes":  # native Mac step; touches no database
        out = Path(rest[0]) if rest else inbox
        print(applenotes.write_notes(applenotes.fetch_notes(), out), "->", out)
        return 0
    if cmd == "tools":  # these two need no database: never create one as a side effect
        for name, t in tools(ALL).items():
            print(f"{name:20} {t.description}")
        return 0
    if cmd == "agents":
        for a in agents.AGENTS:
            print(f"{a.name:9} {len(a.tools)} tools: {', '.join(sorted(a.tools))}")
        return 0
    conn = open_db()
    if cmd == "brief":
        print(json.dumps(briefing_for(conn, date.today()), indent=2, default=str))
    elif cmd == "ingest":
        print(documents.ingest_dir(conn, Path(rest[0]) if rest else Path(os.environ.get("ORBIT_PARSED", Path.home() / "OrbitParsed"))))
    elif cmd == "import-notes":
        print(applenotes.import_dir(conn, Path(rest[0]) if rest else inbox))
    elif cmd == "tag":
        try:
            client = agent.llm.OllamaClient()
            n = tagging.autotag_notes(conn, client, client.resolve(db.get_setting(conn, "model", agent.llm.DEFAULT_MODEL)))
        except RuntimeError:
            n = tagging.autotag_notes(conn)  # model unavailable: rules only
        print(f"tagged {n} note(s)")
    elif cmd == "chat":
        history: list[dict] = []
        client = agent.llm.OllamaClient()
        print("Orbit - Ctrl-D to quit")
        while True:
            try:
                text = input("you> ").strip()
            except EOFError:
                return 0
            if text:
                trace: list = []
                print("orbit>", agent.chat(conn, history, text, client=client, trace=trace))
                print(f"        [{trace[0]['agent']} agent]")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
