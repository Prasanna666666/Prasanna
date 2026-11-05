"""Browsing and finding: filter every payment, open one, and search everything at once. Read-only, exact, and bounded."""

from __future__ import annotations

from typing import Any

from . import categorize, insight
from .db import get_setting


def _like(text: str) -> str:
    return "%" + str(text).replace("\\", "").replace("%", "").replace("_", "") + "%"


def _where(a: dict) -> tuple[str, list]:
    where: list[str] = []
    args: list[Any] = []  # transfers between your own accounts are listed too (they are marked as such), so a payment you look for is never hidden
    if a.get("month"):
        where.append("substr(t.day,1,7)=?")
        args.append(str(a["month"])[:7])
    if a.get("year"):
        where.append("substr(t.day,1,4)=?")
        args.append(str(a["year"])[:4])
    if a.get("category"):
        where.append("t.category=?")
        args.append(str(a["category"]).lower())
    if a.get("kind") in ("expense", "income"):
        where.append("t.kind=?")
        args.append(a["kind"])
    if a.get("query"):
        where.append("(t.note LIKE ? OR t.category LIKE ? OR e.name LIKE ?)")
        args += [_like(a["query"])] * 3
    if a.get("event"):
        where.append("e.name=?")
        args.append(a["event"])
    if a.get("min_amount") is not None:
        where.append("t.amount_minor>=?")
        args.append(round(float(a["min_amount"]) * 100))
    if a.get("max_amount") is not None:
        where.append("t.amount_minor<=?")
        args.append(round(float(a["max_amount"]) * 100))
    return (" WHERE " + " AND ".join(where)) if where else "", args


def explore_payments(conn, a=None):
    """Payments by filter (month, year, category, kind, words, event, amount), newest first or largest first, a page at a time, with the totals of the WHOLE selection."""
    a = a or {}
    clause, args = _where(a)
    base = "FROM ledger t LEFT JOIN events e ON e.id=t.event_id"
    totals = conn.execute(
        f"SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN t.kind='expense' AND t.category<>'transfers' THEN t.amount_minor END),0) AS spent, "
        f"COALESCE(SUM(CASE WHEN t.kind='income' AND t.category<>'transfers' THEN t.amount_minor END),0) AS income {base}{clause}",
        args,
    ).fetchone()
    order = "t.amount_minor DESC, t.day DESC" if a.get("sort") == "amount" else "t.day DESC, t.id DESC"
    limit, offset = max(1, min(int(a.get("limit", 40)), 200)), max(0, int(a.get("offset", 0)))
    rows = conn.execute(
        "SELECT t.id, t.day, t.kind, t.category, t.note, t.amount_minor/100.0 AS amount, t.native_minor/100.0 AS original, "
        "COALESCE(NULLIF(t.currency,''), (SELECT COALESCE((SELECT value FROM settings WHERE key='currency'),'EUR'))) AS currency, e.name AS event, t.sub "
        f"{base}{clause} ORDER BY {order} LIMIT ? OFFSET ?",
        [*args, limit, offset],
    ).fetchall()
    return {
        "count": totals["n"],
        "spent": totals["spent"] / 100,
        "income": totals["income"] / 100,
        "offset": offset,
        "more": offset + len(rows) < totals["n"],
        "rows": [dict(r) for r in rows],
    }


def payment_detail(conn, a):
    """Everything known about one payment: where it came from (file, account), its group, and the payment it refunds or was refunded by."""
    r = conn.execute(
        "SELECT t.id, t.day, t.kind, t.category, t.note, t.amount_minor, t.native_minor, t.currency, t.account, t.source, t.sub, t.auto, t.balance_minor, t.refund_of, t.transfer_id, e.name AS event "
        "FROM ledger t LEFT JOIN events e ON e.id=t.event_id WHERE t.id=?",
        (a["id"],),
    ).fetchone()
    if r is None:
        raise ValueError("no such payment")
    refunded = conn.execute("SELECT id, day, amount_minor/100.0 AS amount FROM transactions WHERE refund_of=?", (r["id"],)).fetchall()
    refund_of = (
        conn.execute("SELECT id, day, note, amount_minor/100.0 AS amount FROM transactions WHERE id=?", (r["refund_of"],)).fetchone()
        if r["refund_of"]
        else None
    )
    same = conn.execute(
        "SELECT COUNT(*) FROM ledger WHERE kind='expense' AND category<>'transfers' AND id<>? AND substr(day,1,7)=substr(?,1,7) AND amount_minor=?",
        (r["id"], r["day"], r["amount_minor"]),
    ).fetchone()[0]
    return {
        "id": r["id"],
        "day": r["day"],
        "kind": r["kind"],
        "note": r["note"],
        "amount": r["amount_minor"] / 100,
        "original": r["native_minor"] / 100,
        "currency": r["currency"] or get_setting(conn, "currency", "EUR"),
        "category": r["category"],
        "category_chosen_by": "you" if not r["auto"] else "automatic",
        "merchant": categorize.merchant(r["note"] or ""),
        "account": ("…" + r["account"][-4:]) if r["account"] else "not known",
        "file": r["source"] or "typed by hand",
        "event": r["event"],
        "sub": r["sub"],
        "balance_after": None if r["balance_minor"] is None else r["balance_minor"] / 100,
        "is_transfer": r["category"] == "transfers" or r["transfer_id"] is not None,
        "refund_of": dict(refund_of) if refund_of else None,
        "refunded_by": [dict(x) for x in refunded],
        "same_amount_this_month": same,
    }


def search_all(conn, a):
    """One box for everything: payments, shops and payees, documents, people, notes and tasks that match the words. A few of each, most relevant first."""
    q = str(a.get("query", "")).strip()
    if len(q) < 2:
        return {"query": q, "payments": [], "merchants": [], "documents": [], "people": [], "notes": [], "tasks": []}
    like = _like(q)
    payments = [
        dict(r)
        for r in conn.execute(
            "SELECT t.id, t.day, t.kind, t.category, t.note, t.amount_minor/100.0 AS amount FROM ledger t WHERE t.note LIKE ? ORDER BY t.day DESC LIMIT 6",
            (like,),
        )
    ]
    al = insight._aliases(conn)
    spend: dict[str, list[float]] = {}
    for r in conn.execute("SELECT note, amount_minor FROM ledger WHERE kind='expense' AND category<>'transfers' AND note LIKE ?", (like,)):
        name = insight._name(al, r["note"])
        if name:
            slot = spend.setdefault(name, [0.0, 0])
            slot[0] += r["amount_minor"] / 100
            slot[1] += 1
    merchants = [{"merchant": m, "spent": round(v[0], 2), "payments": v[1]} for m, v in sorted(spend.items(), key=lambda x: -x[1][0])[:5]]
    documents = [
        dict(r)
        for r in conn.execute(
            "SELECT sha256, name, kind, party, doc_date AS date, total_minor/100.0 AS total FROM finance_docs WHERE name LIKE ? OR party LIKE ? OR title LIKE ? OR reference LIKE ? ORDER BY doc_date DESC LIMIT 6",
            (like, like, like, like),
        )
    ]
    people = [dict(r) for r in conn.execute("SELECT id, name, relation FROM people WHERE name LIKE ? OR relation LIKE ? LIMIT 5", (like, like))]
    notes = [
        dict(r)
        for r in conn.execute(
            "SELECT id, COALESCE(NULLIF(title,''), substr(body,1,40)) AS title FROM notes WHERE title LIKE ? OR body LIKE ? LIMIT 5", (like, like)
        )
    ]
    tasks = [dict(r) for r in conn.execute("SELECT id, title, due FROM tasks WHERE done=0 AND title LIKE ? LIMIT 5", (like,))]
    return {"query": q, "payments": payments, "merchants": merchants, "documents": documents, "people": people, "notes": notes, "tasks": tasks}


def search_links(found: dict) -> list[dict]:
    """The search result as one flat list for Atlas, the shared search: what it is, a line of detail, and the address inside Finance that opens it."""
    from urllib.parse import quote

    out: list[dict] = []
    for m in found.get("merchants", []):
        out.append({"title": m["merchant"], "subtitle": f"{m['payments']} payments", "kind": "shop", "link": "#/expenses?q=" + quote(m["merchant"])})
    for p in found.get("payments", []):
        out.append({"title": p["note"], "subtitle": f"{p['day']} · {p['category']}", "kind": "payment", "link": "#/expenses?q=" + quote(p["note"][:60])})
    for d in found.get("documents", []):
        out.append(
            {"title": d.get("party") or d["name"], "subtitle": f"{d['kind']} · {d.get('date') or ''}".strip(" ·"), "kind": "file", "link": "#/documents"}
        )
    for key, route, kind in (("people", "people", "person"), ("notes", "notes", "note"), ("tasks", "tasks", "task")):
        for x in found.get(key, []):
            out.append(
                {"title": x.get("name") or x.get("title") or "", "subtitle": x.get("relation") or x.get("due") or "", "kind": kind, "link": "#/" + route}
            )
    return [r for r in out if r["title"]]
