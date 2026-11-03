"""Income, expenses and monthly category budgets. Amounts are stored as integer minor units (paise/cents)."""

from __future__ import annotations

from datetime import date

from .. import dates
from ..db import get_setting, rows
from ..module import N, Module, S, Tool

MIGRATIONS = (
    """
    CREATE TABLE transactions (
        id INTEGER PRIMARY KEY,
        day TEXT NOT NULL,
        amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
        kind TEXT NOT NULL CHECK (kind IN ('expense','income')),
        category TEXT NOT NULL DEFAULT 'other',
        note TEXT NOT NULL DEFAULT '',
        created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX tx_day ON transactions(day);
    CREATE TABLE budgets (category TEXT PRIMARY KEY, monthly_minor INTEGER NOT NULL);
    """,
)


def to_minor(x: float) -> int:
    return round(float(x) * 100)


def currency(conn) -> str:
    return get_setting(conn, "currency", "INR")


def add_transaction(conn, a):
    amt = to_minor(a["amount"])
    if amt <= 0:
        raise ValueError("amount must be positive")
    day = a.get("date") or date.today().isoformat()
    dates.parse(day)
    cur = conn.execute(
        "INSERT INTO transactions (day, amount_minor, kind, category, note) VALUES (?,?,?,?,?)",
        (day, amt, a.get("kind", "expense"), a.get("category", "other").strip().lower(), a.get("note", "")),
    )
    conn.commit()
    return {"id": cur.lastrowid, "amount": amt / 100, "currency": currency(conn), "date": day}


def list_transactions(conn, a):
    where, args = [], []
    for col, op, key in (("day", ">=", "since"), ("day", "<=", "until")):
        if a.get(key):
            where.append(f"{col} {op} ?")
            args.append(a[key])
    if a.get("category"):
        where.append("category=?")
        args.append(a["category"].lower())
    sql = "SELECT id, day, kind, category, note, amount_minor/100.0 AS amount FROM transactions"
    sql += " WHERE " + " AND ".join(where) if where else ""
    return rows(conn.execute(sql + " ORDER BY day DESC, id DESC LIMIT ?", [*args, int(a.get("limit", 50))]))


def summary(conn, a):
    start, end = dates.month_bounds(a.get("month") or date.today().strftime("%Y-%m"))
    by_cat = rows(conn.execute(
        "SELECT category, SUM(amount_minor)/100.0 AS spent FROM transactions "
        "WHERE kind='expense' AND day>=? AND day<? GROUP BY category ORDER BY spent DESC", (start, end)))
    tot = {r["kind"]: r["t"] for r in conn.execute(
        "SELECT kind, SUM(amount_minor)/100.0 AS t FROM transactions WHERE day>=? AND day<? GROUP BY kind",
        (start, end))}
    budgets = {r["category"]: r["monthly_minor"] / 100 for r in conn.execute("SELECT * FROM budgets")}
    for r in by_cat:
        if r["category"] in budgets:
            r["budget"], r["left"] = budgets[r["category"]], budgets[r["category"]] - r["spent"]
    return {"month": start[:7], "currency": currency(conn), "spent": tot.get("expense", 0),
            "income": tot.get("income", 0), "net": tot.get("income", 0) - tot.get("expense", 0),
            "by_category": by_cat}


def set_budget(conn, a):
    conn.execute("INSERT OR REPLACE INTO budgets VALUES (?,?)", (a["category"].strip().lower(), to_minor(a["monthly_amount"])))
    conn.commit()
    return {"category": a["category"].lower(), "monthly_amount": a["monthly_amount"]}


def delete_transaction(conn, a):
    conn.execute("DELETE FROM transactions WHERE id=?", (a["id"],))
    conn.commit()
    return {"deleted": a["id"]}


MODULE = Module(
    "money",
    MIGRATIONS,
    (
        Tool("add_transaction", "Record an expense (default) or income. Amount is positive, in the user's currency.",
             {"amount": N("Positive amount"), "kind": S("expense or income", enum=["expense", "income"]),
              "category": S("e.g. groceries, rent, medical, travel, salary"), "note": S("What it was for"),
              "date": S("YYYY-MM-DD, default today")}, add_transaction, ("amount",)),
        Tool("list_transactions", "List transactions, newest first.",
             {"since": S("YYYY-MM-DD"), "until": S("YYYY-MM-DD"), "category": S("Category"), "limit": N("Max rows")},
             list_transactions),
        Tool("spending_summary", "Totals for a month: spent, income, net and per-category spend vs budget.",
             {"month": S("YYYY-MM, default current month")}, summary),
        Tool("set_budget", "Set a monthly budget for a category.",
             {"category": S("Category"), "monthly_amount": N("Amount per month")}, set_budget,
             ("category", "monthly_amount")),
        Tool("delete_transaction", "Delete a transaction by id.", {"id": N("Transaction id")}, delete_transaction, ("id",)),
    ),
)
