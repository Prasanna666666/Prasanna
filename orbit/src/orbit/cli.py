"""orbit ui | chat | brief | tools"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from . import agent, db, netguard
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
                print("orbit>", agent.chat(conn, history, text, client=client))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
