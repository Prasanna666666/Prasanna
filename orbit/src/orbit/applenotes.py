"""Apple Notes -> Orbit, in two separate steps so that nothing sensitive is ever sent anywhere.

1. export (runs natively on the Mac; needs the macOS Notes app): asks Notes for every note via the built-in
   `osascript` and writes one plain-text .md file per note into ~/OrbitInbox/notes/.
2. import (runs anywhere, including inside the Docker container, which sees the inbox read-only): reads those files
   into Orbit's notes table. Re-importing updates changed notes and never duplicates.

Locked notes cannot be read by Notes' scripting interface and are skipped (and counted). Images and attachments are
not exported - only text.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

JXA = """
const Notes = Application('Notes');
const out = [];
for (const f of Notes.folders()) {
  for (const n of f.notes()) {
    const locked = n.passwordProtected();
    out.push({folder: f.name(), id: n.id(), title: n.name(), locked: locked,
              created: n.creationDate().toISOString(), modified: n.modificationDate().toISOString(),
              html: locked ? '' : n.body()});
  }
}
JSON.stringify(out);
"""


# --------------------------------------------------------------------------- html -> text
class _Text(HTMLParser):
    BLOCK = frozenset({"p", "div", "br", "tr", "ul", "ol", "h1", "h2", "h3", "h4", "table"})

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag == "li":
            self.out.append("\n- ")
        elif tag in ("h1", "h2", "h3", "h4"):
            self.out.append("\n\n# ")
        elif tag in ("td", "th"):
            self.out.append(" | ")
        elif tag in ("img", "object"):
            self.out.append(" [attachment] ")  # never keep the (possibly huge) embedded data
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    p = _Text()
    p.feed(html or "")
    text = "".join(p.out).replace("\xa0", " ")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# --------------------------------------------------------------------------- files
def slug(s: str, default: str = "untitled") -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or default


def _one_line(s: str) -> str:
    return " ".join(str(s).split())


def write_notes(records: list[dict], outdir: Path) -> dict[str, int]:
    """Write one .md per unlocked note under outdir/<folder>/. Paths come from slugs only (no traversal)."""
    outdir.mkdir(parents=True, exist_ok=True)
    done = locked = 0
    for r in records:
        if r.get("locked"):
            locked += 1
            continue
        title = _one_line(r.get("title") or "")
        d = outdir / slug(r.get("folder") or "", "unfiled")
        d.mkdir(exist_ok=True)
        name = f"{slug(title)}-{hashlib.sha1(str(r['id']).encode()).hexdigest()[:8]}.md"
        head = "\n".join(
            [
                "---",
                f"title: {title}",
                f"folder: {_one_line(r.get('folder') or '')}",
                f"created: {_one_line(r.get('created') or '')}",
                f"modified: {_one_line(r.get('modified') or '')}",
                f"source_id: {_one_line(r['id'])}",
                "---",
                "",
            ]
        )
        (d / name).write_text(head + html_to_text(r.get("html", "")) + "\n", encoding="utf-8")
        done += 1
    return {"exported": done, "locked_skipped": locked}


def fetch_notes() -> list[dict]:
    if sys.platform != "darwin":
        raise RuntimeError("Exporting needs the macOS Notes app: run `orbit export-notes` on your Mac.")
    try:
        r = subprocess.run(["osascript", "-l", "JavaScript", "-e", JXA], capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Notes took too long to answer (900 s). Try again with Notes open.") from e
    if r.returncode != 0:
        raise RuntimeError(
            "Could not read Notes. If macOS asked, allow your terminal to control Notes "
            f"(System Settings > Privacy & Security > Automation). Details: {r.stderr.strip()[:300]}"
        )
    return json.loads(r.stdout)


def parse_note_file(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
    if not m:
        return None
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(": ")
        meta[k.strip()] = v.strip()
    meta["body"] = m.group(2).strip()
    return meta if meta.get("source_id") and meta["body"] else None


def _ts(iso: str) -> str | None:
    return iso[:19].replace("T", " ") if re.match(r"\d{4}-\d\d-\d\dT", iso or "") else None


# --------------------------------------------------------------------------- import
def import_dir(conn, directory: Path) -> dict[str, int]:
    from .tagging import rule_tags

    people = [dict(r) for r in conn.execute("SELECT name FROM people")]
    new = updated = unchanged = skipped = 0
    root = directory.resolve()
    for f in sorted(root.rglob("*.md")):
        if f.is_symlink() or root not in f.resolve().parents:
            skipped += 1
            continue
        n = parse_note_file(f)
        if not n:
            skipped += 1
            continue
        row = conn.execute("SELECT id, title, body FROM notes WHERE source_id=?", (n["source_id"],)).fetchone()
        if row:
            if row["title"] == n.get("title", "") and row["body"] == n["body"]:
                unchanged += 1
            else:
                conn.execute(
                    "UPDATE notes SET title=?, body=?, updated=COALESCE(?, CURRENT_TIMESTAMP) WHERE id=?",
                    (n.get("title", ""), n["body"], _ts(n.get("modified", "")), row["id"]),
                )
                updated += 1
            continue
        tags = set(rule_tags(f"{n.get('title', '')} {n['body']}", people))
        if n.get("folder"):
            tags.add(slug(n["folder"], "unfiled"))
        conn.execute(
            "INSERT INTO notes (title, body, tags, created, updated, source_id) VALUES (?,?,?,COALESCE(?, CURRENT_TIMESTAMP),COALESCE(?, CURRENT_TIMESTAMP),?)",
            (n.get("title", ""), n["body"], ",".join(sorted(tags)), _ts(n.get("created", "")), _ts(n.get("modified", "")), n["source_id"]),
        )
        new += 1
    conn.commit()
    return {"new": new, "updated": updated, "unchanged": unchanged, "skipped": skipped}
