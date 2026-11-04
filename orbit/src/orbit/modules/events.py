"""Events: named groups of payments, each under one of the main categories (sports, events, trips, cancellations, others) with its own sub-lines.

    Asian Games 2026 (trips): Tickets 634.10, Flights 1179.31, Stay 280.36 ... Total 2438.36
    PSV vs Bayern (cancellations): Tickets 110.00, Refund -175.80 ... Total -65.80

Money paid counts positive and money coming back (a refund) counts negative, so a cancellation can end below zero. Payments that belong to no event
are 'others', broken down by their own sub-category (groceries, rent, subscriptions ...). The local model can PROPOSE groups (nothing is final until
you confirm), but you can always create, rename, move and delete them yourself.
"""

from __future__ import annotations

import json
import re

from .. import audit
from ..db import rows
from ..module import I, Module, S, Tool

MAINS = ("sports", "events", "trips", "cancellations", "others")
SUBS = {"sports": ("tickets", "travel", "food", "merchandise", "stay"), "events": ("tickets", "travel", "food", "stay"),
        "trips": ("flights", "stay", "travel", "tickets", "food and others", "insurance"), "cancellations": ("tickets", "refund", "fees"), "others": ()}

MIGRATIONS = (
    """
    CREATE TABLE events (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL COLLATE NOCASE UNIQUE,
        main TEXT NOT NULL CHECK (main IN ('sports','events','trips','cancellations','others')),
        starts TEXT, ends TEXT,
        confirmed INTEGER NOT NULL DEFAULT 1,   -- 0 = proposed by the model, waiting for you
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    ALTER TABLE transactions ADD COLUMN event_id INTEGER REFERENCES events(id) ON DELETE SET NULL;
    ALTER TABLE transactions ADD COLUMN sub TEXT NOT NULL DEFAULT '';
    CREATE INDEX tx_event ON transactions(event_id);
    """,
    """
    ALTER TABLE transactions ADD COLUMN event_checked INTEGER NOT NULL DEFAULT 0;   -- the model has already looked at this payment
    """,
)


def _event(conn, ref):
    """An event by id or name."""
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        r = conn.execute("SELECT * FROM events WHERE id=?", (int(ref),)).fetchone()
        if r:
            return r
    return conn.execute("SELECT * FROM events WHERE name=?", (str(ref).strip(),)).fetchone()


def create_event(conn, a, confirmed: int = 1):
    name = " ".join(str(a.get("name", "")).split())[:80]
    if not name:
        raise ValueError("an event needs a name")
    main = str(a.get("main") or "events").lower()
    if main not in MAINS:
        raise ValueError(f"main category must be one of: {', '.join(MAINS)}")
    existing = _event(conn, name)
    if existing:
        return {"id": existing["id"], "name": existing["name"], "main": existing["main"], "created": False}
    cur = conn.execute("INSERT INTO events (name, main, starts, ends, confirmed) VALUES (?,?,?,?,?)", (name, main, a.get("start"), a.get("end"), confirmed))
    conn.commit()
    return {"id": cur.lastrowid, "name": name, "main": main, "created": True}


def update_event(conn, a):
    ev = _event(conn, a["id"])
    if ev is None:
        raise ValueError("no such event")
    name = " ".join(str(a.get("name") or ev["name"]).split())[:80]
    main = str(a.get("main") or ev["main"]).lower()
    if main not in MAINS:
        raise ValueError(f"main category must be one of: {', '.join(MAINS)}")
    conn.execute("UPDATE events SET name=?, main=?, starts=COALESCE(?,starts), ends=COALESCE(?,ends), confirmed=? WHERE id=?",
                 (name, main, a.get("start"), a.get("end"), 1 if a.get("confirmed", True) else 0, ev["id"]))
    conn.commit()
    audit.record(conn, "event changed", f"{ev['name']} -> {name} ({main})")
    return {"id": ev["id"], "name": name, "main": main}


def delete_event(conn, a):
    ev = _event(conn, a["id"])
    if ev is None:
        raise ValueError("no such event")
    conn.execute("UPDATE transactions SET event_id=NULL, sub='' WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM events WHERE id=?", (ev["id"],))
    conn.commit()
    audit.record(conn, "event deleted", ev["name"])
    return {"deleted": ev["name"]}


def assign(conn, a, confirmed: int = 1):
    """Put payments into an event under a sub-category. The event is created (under `main`) if it does not exist yet."""
    ids = [int(i) for i in (a.get("transaction_ids") or []) if str(i).lstrip("-").isdigit()]
    if not ids:
        raise ValueError("no payments were chosen")
    ev = _event(conn, a["event"])
    if ev is None:
        made = create_event(conn, {"name": a["event"], "main": a.get("main") or "events"}, confirmed)
        ev = _event(conn, made["id"])
    sub = " ".join(str(a.get("sub") or "").split())[:40].lower()
    moved = 0
    for i in ids:
        t = conn.execute("SELECT kind, category FROM transactions WHERE id=?", (i,)).fetchone()
        if t is None:
            continue
        chosen = sub or ("refund" if t["kind"] == "income" else (t["category"] if t["category"] != "other" else ""))
        conn.execute("UPDATE transactions SET event_id=?, sub=? WHERE id=?", (ev["id"], chosen, i))
        moved += 1
    conn.commit()
    audit.record(conn, "payments added to an event", f"{ev['name']}: {moved}")
    return {"event": ev["name"], "id": ev["id"], "payments": moved}


def unassign(conn, a):
    ids = [int(i) for i in (a.get("transaction_ids") or []) if str(i).lstrip("-").isdigit()]
    for i in ids:
        conn.execute("UPDATE transactions SET event_id=NULL, sub='' WHERE id=?", (i,))
    conn.commit()
    return {"payments": len(ids)}


def _lines(conn, event_id):
    out = rows(conn.execute(
        "SELECT CASE WHEN sub='' THEN 'other' ELSE sub END AS sub, "
        "ROUND(SUM(CASE WHEN kind='income' THEN -amount_minor ELSE amount_minor END)/100.0, 2) AS amount, COUNT(*) AS payments "
        "FROM ledger WHERE event_id=? GROUP BY 1 ORDER BY (sub='refund'), amount DESC", (event_id,)))
    return out


def list_events(conn, a=None):
    """Events grouped by main category, each with its sub-lines and total (refunds negative), newest first."""
    a = a or {}
    where, args = [], []
    if a.get("main"):
        where.append("e.main=?")
        args.append(str(a["main"]).lower())
    sql = ("SELECT e.id, e.name, e.main, e.confirmed, e.starts, e.ends, MIN(t.day) AS first, MAX(t.day) AS last FROM events e LEFT JOIN ledger t ON t.event_id=e.id"
           + (" WHERE " + " AND ".join(where) if where else "") + " GROUP BY e.id ORDER BY MAX(t.day) DESC, e.name")
    out = rows(conn.execute(sql, args))
    for ev in out:
        ev["lines"] = _lines(conn, ev["id"])
        ev["total"] = round(sum(x["amount"] for x in ev["lines"]), 2)
        ev["payments"] = sum(x["payments"] for x in ev["lines"])
    order = {m: i for i, m in enumerate(MAINS)}
    return sorted(out, key=lambda e: order[e["main"]])


def spending_by_main(conn, a=None):
    """Net cost per main category (refunds subtracted), for a month if given. 'others' is everything that is in no event, split by sub-category."""
    from .. import dates

    a = a or {}
    span, args = "", []
    if a.get("month"):
        start, end = dates.month_bounds(a["month"])
        span, args = " AND t.day>=? AND t.day<?", [start, end]
    net = "SUM(CASE WHEN t.kind='income' THEN -t.amount_minor ELSE t.amount_minor END)/100.0"
    ev = {r["main"]: r for r in rows(conn.execute(
        f"SELECT e.main AS main, ROUND({net}, 2) AS net, COUNT(DISTINCT e.id) AS events FROM ledger t JOIN events e ON e.id=t.event_id "
        f"WHERE 1=1{span} GROUP BY e.main", args))}
    others = rows(conn.execute(
        f"SELECT CASE WHEN t.category='other' THEN 'unsorted' ELSE t.category END AS sub, ROUND(SUM(t.amount_minor)/100.0, 2) AS amount FROM ledger t "
        f"WHERE t.event_id IS NULL AND t.kind='expense' AND t.category<>'transfers'{span} GROUP BY 1 ORDER BY amount DESC", args))
    out = [{"main": m, "net": (ev.get(m) or {}).get("net", 0.0), "events": (ev.get(m) or {}).get("events", 0)} for m in MAINS if m != "others"]
    out.append({"main": "others", "net": round(sum(o["amount"] for o in others), 2), "events": 0, "subs": others})
    return out


def daily_by_category(conn, a=None):
    """Day-to-day spending by category (groceries, food, shopping, transport ...) for a month: payments in no event, own-account moves left out.
    Each row also carries the month before, for comparison."""
    from datetime import date

    from .. import dates

    a = a or {}
    month = a.get("month") or date.today().strftime("%Y-%m")
    start, end = dates.month_bounds(month)
    before_start = dates.add_months(date.fromisoformat(start), -1).isoformat()

    def totals(lo, hi):
        return {r["sub"]: (r["amount"], r["n"]) for r in rows(conn.execute(
            "SELECT CASE WHEN category='other' THEN 'unsorted' ELSE category END AS sub, ROUND(SUM(amount_minor)/100.0, 2) AS amount, COUNT(*) AS n FROM ledger "
            "WHERE event_id IS NULL AND kind='expense' AND category<>'transfers' AND day>=? AND day<? GROUP BY 1", (lo, hi)))}

    now, before = totals(start, end), totals(before_start, start)
    out = [{"category": c, "amount": v[0], "payments": v[1], "before": before.get(c, (0.0, 0))[0]} for c, v in now.items()]
    return sorted(out, key=lambda r: -r["amount"])


# ---- the model proposes groups -------------------------------------------------------------------------------------------
ROUTINE = ("rent", "emi", "insurance", "utilities", "salary", "interest", "groceries", "fuel", "cash", "fees", "transfers", "investments", "medical", "education",
           "subscriptions")
SCHEMA = {"type": "object", "properties": {"assignments": {"type": "array", "items": {"type": "object", "properties": {
    "id": {"type": "integer"}, "event": {"type": "string"}, "main": {"type": "string", "enum": list(MAINS)}, "sub": {"type": "string"}},
    "required": ["id", "event", "main"]}}}, "required": ["assignments"]}
PROMPT = (
    "You group a person's payments into named events. The main categories are: sports (matches, games, tournaments), events (concerts, shows, festivals), "
    "trips (travel: flights, hotels, tours), cancellations (an event or trip that was cancelled, with its refund), and others. Each line is: id | date | "
    "amount (minus = money paid, plus = money received) | description. Payments that clearly belong to the SAME event or trip share one short event name "
    "(for example 'Asian Games 2026' or 'Max Amini'); give each a sub-category (tickets, flights, stay, travel, food, refund ...). A refund for a "
    "cancelled event goes in the same event, main 'cancellations'. Everyday spending (shops, bills, subscriptions) belongs to no event: use event ''. "
    "Reuse an existing event name when it fits: "
)
CHUNK = 20


def suggest(conn, client, model: str, progress=None) -> dict:
    """Ask the local model to attach new payments to events. Runs by itself after every import; each payment is looked at once."""
    todo = rows(conn.execute(
        "SELECT id, day, kind, note, category, ROUND(amount_minor/100.0, 2) AS amount FROM transactions WHERE event_id IS NULL AND event_checked=0 AND category NOT IN (%s) ORDER BY day"
        % ",".join("?" * len(ROUTINE)), ROUTINE))
    grouped = 0
    for n in range(0, len(todo), CHUNK):
        chunk = todo[n:n + CHUNK]
        known = ", ".join(f"{e['name']} ({e['main']})" for e in rows(conn.execute("SELECT name, main FROM events"))) or "none yet"
        text = "\n".join(f"{t['id']} | {t['day']} | {'+' if t['kind'] == 'income' else '-'}{t['amount']} | {t['note']}" for t in chunk)
        if progress:
            progress("Sorting your payments")
        msg = client.chat(model, [{"role": "system", "content": PROMPT + known + "."}, {"role": "user", "content": text}], schema=SCHEMA)
        try:
            items = json.loads(msg.get("content") or "{}").get("assignments", [])
        except ValueError:
            continue
        conn.executemany("UPDATE transactions SET event_checked=1 WHERE id=?", [(t["id"],) for t in chunk])  # never ask about the same payment twice
        conn.commit()
        valid = {t["id"] for t in chunk}
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict) or it.get("id") not in valid:
                continue
            name = re.sub(r"\s+", " ", str(it.get("event") or "")).strip()[:80]
            if not name or it.get("main") not in MAINS or it["main"] == "others":
                continue
            assign(conn, {"transaction_ids": [it["id"]], "event": name, "main": it["main"], "sub": str(it.get("sub") or "")}, confirmed=1)
            grouped += 1
    return {"considered": len(todo), "grouped": grouped, "events": len(rows(conn.execute("SELECT 1 FROM events WHERE confirmed=0")))}


MODULE = Module("events", MIGRATIONS, (
    Tool("list_events", "Events grouped by main category (sports, events, trips, cancellations), each with sub-lines (tickets, flights, stay, refund ...) and a total.",
         {"main": S("sports, events, trips, cancellations or others", enum=list(MAINS))}, list_events),
    Tool("create_event", "Create a named event under a main category.", {"name": S("e.g. Asian Games 2026"), "main": S("Main category", enum=list(MAINS)),
                                                                           "start": S("YYYY-MM-DD"), "end": S("YYYY-MM-DD")}, create_event, ("name",)),
    Tool("assign_to_event", "Put payments (by transaction id) into an event with a sub-category such as tickets, flights, stay, travel, food, refund.",
         {"event": S("Event name or id (created if new)"), "main": S("Main category if the event is new", enum=list(MAINS)),
          "sub": S("Sub-category"), "transaction_ids": {"type": "array", "items": {"type": "integer"}, "description": "Transaction ids"}}, assign, ("event", "transaction_ids")),
    Tool("remove_from_event", "Take payments out of their event.", {"transaction_ids": {"type": "array", "items": {"type": "integer"}, "description": "Transaction ids"}},
         unassign, ("transaction_ids",)),
    Tool("update_event", "Rename an event, change its main category, or confirm a proposed one.", {"id": I("Event id"), "name": S("New name"),
                                                                                                  "main": S("Main category", enum=list(MAINS)), "confirmed": {"type": "boolean", "description": "true to accept"}},
         update_event, ("id",)),
    Tool("delete_event", "Delete an event (its payments stay, ungrouped).", {"id": I("Event id")}, delete_event, ("id",)),
    Tool("daily_spending", "Day-to-day spending by category (groceries, food, shopping, transport ...) for a month YYYY-MM, with the month before for comparison.",
         {"month": S("YYYY-MM")}, daily_by_category),
    Tool("spending_by_main", "Net cost per main category (refunds subtracted) for a month YYYY-MM, with 'others' split by sub-category.",
         {"month": S("YYYY-MM")}, spending_by_main),
))
