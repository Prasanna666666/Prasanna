"""Apple Mail -> the inbox folder, as plain .eml files, so nothing sensitive is ever sent anywhere.

Apple Mail already keeps your mail on this Mac (it does the talking to Gmail, Outlook or iCloud, as it always has). This step only asks the Mail app
for the messages you choose, through the built-in `osascript`, and writes each one as a .eml file into ~/OrbitInbox/mail/. The isolated reader (no
network, inbox read-only) then reads the messages and their attachments like any other document. Nothing here connects to a mail server.

Choose what to export: the last N days (default 365), and by default only messages that have an attachment (invoices, tickets, payslips, reports), so
the rest of your mailbox is never copied. Junk, Trash and Drafts are always skipped. Re-running adds only what is new.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SKIP_MAILBOXES = ["Junk", "Junk E-mail", "Spam", "Trash", "Deleted Messages", "Deleted Items", "Drafts"]
MAX_MESSAGE_CHARS = 30_000_000

JXA = """
const Mail = Application('Mail');
const P = __PARAMS__;
const cutoff = new Date(Date.now() - P.days * 86400000);
const out = [];
for (const acct of Mail.accounts()) {
  for (const mb of acct.mailboxes()) {
    const name = mb.name();
    if (P.skip.includes(name)) continue;
    let msgs;
    try { msgs = mb.messages.whose({dateReceived: {'>': cutoff}})(); } catch (e) { continue; }
    for (const m of msgs) {
      let attachments = 0;
      try { attachments = m.mailAttachments().length; } catch (e) {}
      if (P.only_attachments && attachments === 0) continue;
      let source = '';
      try { source = m.source(); } catch (e) { continue; }
      out.push({account: acct.name(), mailbox: name, id: String(m.id()), source: source});
    }
  }
}
JSON.stringify(out);
"""


def build_script(days: int, only_attachments: bool) -> str:
    """The Mail script with its few settings written in (numbers, a flag and a fixed list: nothing the user typed goes into the code)."""
    params = {"days": max(1, min(int(days), 3650)), "only_attachments": bool(only_attachments), "skip": SKIP_MAILBOXES}
    return JXA.replace("__PARAMS__", json.dumps(params))


def fetch_messages(days: int = 365, only_attachments: bool = True, run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> list[dict]:
    if sys.platform != "darwin" and run is subprocess.run:
        raise RuntimeError("Exporting needs the macOS Mail app: run `orbit export-mail` on your Mac.")
    try:
        r = run(["osascript", "-l", "JavaScript", "-e", build_script(days, only_attachments)], capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Mail took too long to answer (30 minutes). Try fewer days, or open Mail first.") from e
    if r.returncode != 0:
        raise RuntimeError(
            "Could not read Mail. If macOS asked, allow your terminal to control Mail "
            f"(System Settings > Privacy & Security > Automation). Details: {r.stderr.strip()[:300]}"
        )
    records = json.loads(r.stdout or "[]")
    if not isinstance(records, list):
        raise RuntimeError("Mail answered in a form I do not understand.")
    return records


def write_messages(records: list[dict], outdir: Path) -> dict[str, int]:
    """One <hash>.eml per message. The name comes from a hash of the account and message id, never from the mail's own text; existing files are kept."""
    outdir.mkdir(parents=True, exist_ok=True)
    new = known = skipped = 0
    for r in records:
        source = r.get("source") if isinstance(r, dict) else None
        if not isinstance(source, str) or not source.strip() or len(source) > MAX_MESSAGE_CHARS:
            skipped += 1
            continue
        key = f"{r.get('account', '')}|{r.get('mailbox', '')}|{r.get('id', '')}"
        target = outdir / f"{hashlib.sha1(key.encode(), usedforsecurity=False).hexdigest()}.eml"
        if target.exists():
            known += 1
            continue
        target.write_bytes(source.encode("utf-8", errors="replace"))
        new += 1
    return {"new": new, "already_had": known, "skipped": skipped}
