"""What you own and owe. Account balances come ONLY from proven statements; everything else (a house, a car, a loan, shares) is typed by you, kept apart,
and always labelled as entered by you, so a number Orbit proved is never mixed up with one it was told."""

from __future__ import annotations

from datetime import date

from . import clock, insight, rates
from .db import get_setting

KINDS = ("investment", "asset", "debt")


def _main(conn) -> str:
    return get_setting(conn, "currency", "EUR")


def add_holding(conn, a):
    """Something you typed in: an investment (units and price, or a value), an asset (house, car) or a debt (loan, mortgage)."""
    kind = str(a.get("kind", "")).lower()
    name = str(a.get("name", "")).strip()
    if kind not in KINDS or not name:
        raise ValueError("a holding needs a name and a kind: investment, asset or debt")
    if a.get("units") is not None and a.get("price") is not None:
        value = round(float(a["units"]) * float(a["price"]) * 100)
    elif a.get("value") is not None:
        value = round(float(a["value"]) * 100)
    else:
        raise ValueError("give a value, or units and a price")
    if value < 0:
        raise ValueError("a value cannot be negative: debts are entered as a positive amount owed")
    cost = None if a.get("cost") is None else round(float(a["cost"]) * 100)
    if cost is not None and cost < 0:
        raise ValueError("the amount paid in cannot be negative")
    as_of = str(a.get("as_of") or clock.today().isoformat())
    date.fromisoformat(as_of)
    currency = str(a.get("currency") or _main(conn)).upper()[:5]
    cur = conn.execute(
        "INSERT INTO holdings (name, kind, value_minor, units, price_minor, currency, as_of, cost_minor) VALUES (?,?,?,?,?,?,?,?)",
        (name[:80], kind, value, a.get("units"), round(float(a["price"]) * 100) if a.get("price") is not None else None, currency, as_of, cost),
    )
    conn.commit()
    return {"id": cur.lastrowid, "name": name, "kind": kind, "value": value / 100, "currency": currency, "as_of": as_of}


def update_holding(conn, a):
    """A new value for something you typed in earlier (the price moved, the loan went down). The old value is replaced and the date updated."""
    row = conn.execute("SELECT * FROM holdings WHERE id=?", (a["id"],)).fetchone()
    if row is None:
        raise ValueError("no such holding")
    if a.get("units") is not None and a.get("price") is not None:
        value, units, price = round(float(a["units"]) * float(a["price"]) * 100), a["units"], round(float(a["price"]) * 100)
    elif a.get("price") is not None and row["units"] is not None:
        units, price = row["units"], round(float(a["price"]) * 100)
        value = round(units * price)
    elif a.get("value") is not None:
        value, units, price = round(float(a["value"]) * 100), row["units"], row["price_minor"]
    elif a.get("cost") is not None:  # only what was paid in changes
        value, units, price = row["value_minor"], row["units"], row["price_minor"]
    else:
        raise ValueError("give a new value, price or amount paid in")
    cost = row["cost_minor"] if a.get("cost") is None else round(float(a["cost"]) * 100)
    conn.execute(
        "UPDATE holdings SET value_minor=?, units=?, price_minor=?, cost_minor=?, as_of=? WHERE id=?",
        (value, units, price, cost, a.get("as_of") or clock.today().isoformat(), a["id"]),
    )
    conn.commit()
    return {"id": a["id"], "value": value / 100}


def delete_holding(conn, a):
    conn.execute("DELETE FROM holdings WHERE id=?", (a["id"],))
    conn.commit()
    return {"deleted": a["id"]}


def _eur_or_same(conn, minor: int, currency: str, day: str):
    """The amount in the main currency: unchanged if it already is, converted at that day's rate if not, None if no rate is known."""
    if currency == _main(conn) or currency == "EUR":
        return minor
    found = rates.rate_on(conn, currency, day)
    return rates.to_eur(minor, found[0]) if found else None


def list_holdings(conn, a=None):
    out = []
    for r in conn.execute("SELECT id, name, kind, value_minor, units, price_minor, currency, as_of, cost_minor FROM holdings ORDER BY kind, name"):
        out.append(
            {
                "cost": None if r["cost_minor"] is None else r["cost_minor"] / 100,
                "gain": None if r["cost_minor"] is None else (r["value_minor"] - r["cost_minor"]) / 100,
                "id": r["id"],
                "name": r["name"],
                "kind": r["kind"],
                "value": r["value_minor"] / 100,
                "units": r["units"],
                "price": None if r["price_minor"] is None else r["price_minor"] / 100,
                "currency": r["currency"],
                "as_of": r["as_of"],
                "entered_by_you": True,
            }
        )
    return out


def accounts_overview(conn, a=None):
    """Each account with the balance from its latest proven statement, and whether every statement of it passed its checks."""
    accounts = insight.net_worth(conn)["accounts"]
    out = []
    for acc in accounts:
        files = conn.execute(
            "SELECT COUNT(*) AS n, SUM(status='verified') AS ok, MAX(period_end) AS last FROM statement_files WHERE account=?", (acc["account"],)
        ).fetchone()
        out.append({**acc, "statements": files["n"], "proven": files["n"] == (files["ok"] or 0), "label": "…" + acc["account"][-4:]})
    return out


def wealth_summary(conn, a=None):
    """Net worth = accounts (proven) + investments, assets (typed by you) - debts (typed by you). Each part is shown on its own."""
    nw = insight.net_worth(conn)
    accounts = nw["latest"]
    parts = {"investment": 0, "asset": 0, "debt": 0}
    unconverted = 0
    for h in conn.execute("SELECT kind, value_minor, currency, as_of FROM holdings"):
        v = _eur_or_same(conn, h["value_minor"], h["currency"], h["as_of"])
        if v is None:
            unconverted += 1
        else:
            parts[h["kind"]] += v
    total = (accounts or 0) + (parts["investment"] + parts["asset"] - parts["debt"]) / 100
    return {
        "currency": "EUR" if _main(conn) == "EUR" else _main(conn),
        "net_worth": round(total, 2) if accounts is not None or any(parts.values()) else None,
        "accounts": accounts,
        "investments": parts["investment"] / 100,
        "assets": parts["asset"] / 100,
        "debts": parts["debt"] / 100,
        "series": nw["series"],
        "not_converted": unconverted,
        "note": "Accounts come from proven statements. Investments, assets and debts are the values you typed in, as of the date shown with each.",
    }


def investments_overview(conn, a=None):
    """What went into investments, what it is worth now, and the gain or loss. Contributions are counted from your payments; the value is what you typed in
    (Orbit cannot read a broker's statement), and a gain or loss is shown only for holdings where you also typed what you paid in."""
    from . import planning

    held = [h for h in list_holdings(conn) if h["kind"] == "investment"]
    value = sum(h["value"] for h in held)
    with_cost = [h for h in held if h["cost"] is not None]
    cost = sum(h["cost"] for h in with_cost)
    gain = sum(h["gain"] for h in with_cost)
    paid = planning.investments(conn)
    return {
        "currency": _main(conn),
        "contributed_total": round(sum(y["contributed"] for y in paid["contributed_by_year"]), 2),
        "contributed_by_year": paid["contributed_by_year"],
        "value": round(value, 2),
        "holdings": held,
        "cost": round(cost, 2) if with_cost else None,
        "gain": round(gain, 2) if with_cost else None,
        "gain_percent": round(gain / cost * 100, 1) if with_cost and cost else None,
        "complete": len(with_cost) == len(held),
        "note": "Contributions come from your payments. Values and costs are what you typed in. A gain or loss needs the amount paid in for the holding.",
    }
