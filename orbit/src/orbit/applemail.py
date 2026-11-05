"""Apple Mail -> the inbox folder, as plain .eml files, so nothing sensitive is ever sent anywhere.

Apple Mail already keeps your mail on this Mac (it does the talking to Gmail, Outlook or iCloud, as it always has). This step only asks the Mail app
for the messages, through the built-in `osascript`, and writes each one as a .eml file into ~/OrbitInbox/mail/. The isolated reader (no network,
inbox read-only) then reads the messages, their text and their attachments, like any other document. Nothing here connects to a mail server.

All mail of the last N days (default 3650, ten years) is copied, one mailbox at a time, because the text of an email is often the crucial information (a booking
time, a payment confirmation, an appointment). Junk, Trash and Drafts are always skipped. `only_attachments` narrows it to messages with an attachment.
Re-running adds only what is new.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

SKIP_MAILBOXES = frozenset(["Junk", "Junk E-mail", "Spam", "Trash", "Deleted Messages", "Deleted Items", "Drafts"])
MAX_MESSAGE_CHARS = 30_000_000
Runner = Callable[..., "subprocess.CompletedProcess[str]"]

LIST_JXA = """
const Mail = Application('Mail');
const out = [];
for (const acct of Mail.accounts()) {
  for (const mb of acct.mailboxes()) { out.push({account: acct.name(), mailbox: mb.name()}); }
}
JSON.stringify(out);
"""

MAILBOX_JXA = """
const Mail = Application('Mail');
const P = __PARAMS__;
const cutoff = new Date(Date.now() - P.days * 86400000);
const out = [];
let msgs = [];
try {
  const mb = Mail.accounts.byName(P.account).mailboxes.byName(P.mailbox);
  msgs = mb.messages.whose({dateReceived: {'>': cutoff}})();
} catch (e) {}
for (const m of msgs) {
  if (P.only_attachments) {
    let attachments = 0;
    try { attachments = m.mailAttachments().length; } catch (e) {}
    if (attachments === 0) continue;
  }
  let source = '';
  try { source = m.source(); } catch (e) { continue; }
  out.push({account: P.account, mailbox: P.mailbox, id: String(m.id()), source: source});
}
JSON.stringify(out);
"""


def build_script(account: str, mailbox: str, days: int, only_attachments: bool) -> str:
    """The Mail script for one mailbox. Its settings are written in as a JSON literal (names are data there, never code)."""
    params = {"account": account, "mailbox": mailbox, "days": max(1, min(int(days), 18250)), "only_attachments": bool(only_attachments)}
    return MAILBOX_JXA.replace("__PARAMS__", json.dumps(params))


def _run(script: str, run: Runner, timeout: int) -> list:
    if sys.platform != "darwin" and run is subprocess.run:
        raise RuntimeError("Exporting needs the macOS Mail app: run `orbit export-mail` on your Mac.")
    try:
        r = run(["osascript", "-l", "JavaScript", "-e", script], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Mail took too long to answer ({timeout // 60} minutes). Try fewer days, or open Mail first.") from e
    if r.returncode != 0:
        raise RuntimeError(
            "Could not read Mail. If macOS asked, allow your terminal to control Mail "
            f"(System Settings > Privacy & Security > Automation). Details: {r.stderr.strip()[:300]}"
        )
    records = json.loads(r.stdout or "[]")
    if not isinstance(records, list):
        raise RuntimeError("Mail answered in a form I do not understand.")
    return records


def list_mailboxes(run: Runner = subprocess.run) -> list[tuple[str, str]]:
    """Every (account, mailbox) except Junk, Trash and Drafts."""
    found = _run(LIST_JXA, run, 300)
    return [(str(m["account"]), str(m["mailbox"])) for m in found if isinstance(m, dict) and m.get("mailbox") not in SKIP_MAILBOXES]


def fetch_mailbox(account: str, mailbox: str, days: int = 3650, only_attachments: bool = False, run: Runner = subprocess.run) -> list[dict]:
    return _run(build_script(account, mailbox, days, only_attachments), run, 1800)


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


def export(
    outdir: Path, days: int = 3650, only_attachments: bool = False, run: Runner = subprocess.run, progress: Callable[[str], None] = print
) -> dict[str, int]:
    """Copy the mail, mailbox by mailbox (each written before the next is asked for), and say where it is."""
    total = {"new": 0, "already_had": 0, "skipped": 0, "mailboxes": 0}
    for account, mailbox in list_mailboxes(run):
        got = write_messages(fetch_mailbox(account, mailbox, days, only_attachments, run), outdir)
        total["mailboxes"] += 1
        for key in ("new", "already_had", "skipped"):
            total[key] += got[key]
        progress(f"  {account} / {mailbox}: {got['new']} new, {got['already_had']} already had")
    return total
