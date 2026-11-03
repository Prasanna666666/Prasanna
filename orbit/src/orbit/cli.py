"""orbit ui | chat | brief | tools | agents | tag"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import agent, agents, db, netguard, tagging
from .modules import ALL, tools
from .modules.today import briefing_for


def open_db():
    conn = db.connect()
    db.migrate(conn, ALL)
    return conn


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:]) or ["ui"]
    cmd, rest = args[0], args[1:]
    if cmd == "ui":
        app = Path(__file__).with_name("app.py")
        return subprocess.call([sys.executable, "-m", "streamlit", "run", str(app), *rest])
    netguard.install()
    conn = open_db()
    if cmd == "brief":
        print(json.dumps(briefing_for(conn, date.today()), indent=2, default=str))
    elif cmd == "tools":
        for name, t in tools(ALL).items():
            print(f"{name:20} {t.description}")
    elif cmd == "agents":
        for a in agents.AGENTS:
            print(f"{a.name:9} {len(a.tools)} tools: {', '.join(sorted(a.tools))}")
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
