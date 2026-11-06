"""library serve [--host H] [--port P] | export-mail [dir] [--days N] [--attachments-only]"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import applemail, web


def _mail_inbox() -> Path:
    return Path(os.environ.get("ATLAS_INBOX", Path.home() / "AtlasInbox")) / "mail"


def _serve(rest: list[str]) -> int:
    host = rest[rest.index("--host") + 1] if "--host" in rest else "127.0.0.1"
    port = int(rest[rest.index("--port") + 1]) if "--port" in rest else 8502
    return web.serve(host, port)


def _export_mail(rest: list[str]) -> int:  # a native Mac step: copies your mail into the inbox as .eml files; connects to no mail server
    days = int(rest[rest.index("--days") + 1]) if "--days" in rest else None
    only_attachments = "--attachments-only" in rest  # by default ALL mail: the text of an email is often the crucial information
    folders = [a for i, a in enumerate(rest) if not a.startswith("--") and (i == 0 or rest[i - 1] != "--days")]
    out = Path(folders[0]) if folders else _mail_inbox()
    print(applemail.export(out, days, only_attachments), "->", out)
    return 0


COMMANDS = {"serve": _serve, "export-mail": _export_mail}


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] not in COMMANDS:
        print(__doc__)
        return 2
    return COMMANDS[args[0]](args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
