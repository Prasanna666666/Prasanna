"""Fills a throw-away Documents database with N synthetic documents and times the questions the pages ask. Run from library/: python ../scripts/scale-check.py 300000"""

import json, os, sys, tempfile, time, random
from pathlib import Path

sys.path[:0] = ["src", "../kit/src"]
from kit import db
from library import store, scanstatus, appstate, healthdata

N = int(sys.argv[1])
home = Path(tempfile.mkdtemp())
os.environ["ATLAS_HOME"] = str(home)
conn = db.connect(home / "library.db", timeout=60)
db.migrate(conn, [store.MODULE])
random.seed(1)
kinds = [
    "invoice",
    "payslip",
    "email",
    "bank_statement",
    "ticket",
    "receipt",
    "letter",
    "other",
]
rows = []
for i in range(N):
    area = random.choice(["mail", "finance", "health", "travel", "inbox"])
    kind = "email" if area == "mail" and i % 3 else random.choice(kinds)
    rows.append(
        (
            f"sha{i}",
            f"{area}/file{i}.pdf",
            kind,
            f"title {i}",
            area,
            json.dumps({"title": f"t{i}", "date": "2025-01-01", "total": 12.5}),
            random.choice([0, 1, 2]),
            None,
        )
    )
t = time.time()
conn.executemany(
    "INSERT INTO documents (sha256, name, kind, text, area, facts, judged, case_id, ready, parsed_at) VALUES (?,?,?,?,?,?,?,?,1,'2025-01-01')",
    rows,
)
conn.commit()
print(f"insert {N}: {time.time() - t:.1f}s")


def timed(label, fn):
    t = time.time()
    r = fn()
    print(f"{label}: {time.time() - t:.2f}s")
    return r


timed("tally (status counts)", lambda: scanstatus._tally(conn))
timed("counts", lambda: store.counts(conn))
print(len(timed("by_kind", lambda: store.by_kind(conn))), "kinds")
print(
    len(
        timed(
            "list_documents page",
            lambda: store.list_documents(conn, area="finance", limit=50),
        )
    ),
    "rows",
)
timed("health_documents", lambda: healthdata.health_documents(conn))
timed("held_back", lambda: store.held_back(conn, "health", []))
