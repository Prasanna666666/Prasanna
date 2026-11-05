"""Euro conversion at the rate of the day. Rates are the ECB's published daily reference rates (foreign currency per 1 EUR), stored locally.

Finance is offline, so the rates come from a file you load once: `scripts/fetch-rates.sh` (run on the Mac, outside Docker, the only step that goes online) downloads the ECB history into your
finance folder; the next "Read my files" loads it. Nothing is converted with a made-up number: a payment with no rate for its day (or the days just before it)
stays unconverted, is left out of 'all in euros' totals, and is reported.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

REPORTING = "EUR"
MAX_AGE_DAYS = 7  # weekends and bank holidays have no ECB rate: the last published one is used, up to a week back


def looks_like_ecb(rows) -> bool:
    return bool(rows) and isinstance(rows[0], list) and len(rows[0]) > 3 and str(rows[0][0]).strip() == "Date" and "USD" in [str(c).strip() for c in rows[0]]


def parse_ecb(rows: list[list]) -> list[tuple[str, str, str]]:
    """(day, currency, units per 1 EUR) from the rows of the ECB's eurofxref CSV (history or daily). 'N/A' cells are skipped."""
    head = [str(c).strip() for c in rows[0]]
    out = []
    for r in rows[1:]:
        try:
            day = date.fromisoformat(str(r[0]).strip()).isoformat()
        except (ValueError, IndexError):
            continue
        for cur, v in zip(head[1:], r[1:], strict=False):
            v = str(v).strip()
            if cur and v and v.upper() != "N/A":
                try:
                    if Decimal(v) > 0:
                        out.append((day, cur, v))
                except InvalidOperation:
                    continue
    return out


def store(conn, found: list[tuple[str, str, str]]) -> int:
    conn.executemany("INSERT OR REPLACE INTO rates (day, currency, per_eur) VALUES (?,?,?)", found)
    conn.commit()
    return len(found)


def rate_on(conn, currency: str, day: str) -> tuple[Decimal, str] | None:
    """(units of `currency` per 1 EUR, the day that rate is from) for the payment's day or the last one before it (within a week)."""
    lo = (date.fromisoformat(day) - timedelta(days=MAX_AGE_DAYS)).isoformat()
    r = conn.execute("SELECT per_eur, day FROM rates WHERE currency=? AND day<=? AND day>=? ORDER BY day DESC LIMIT 1", (currency, day, lo)).fetchone()
    return (Decimal(r["per_eur"]), r["day"]) if r else None


def to_eur(minor: int, per_eur: Decimal) -> int:
    """Minor units of a foreign currency -> euro cents at `per_eur` units per euro, rounded half-even (exact decimal arithmetic)."""
    return int((Decimal(minor) / per_eur).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def convert_all(conn) -> dict[str, int]:
    """Give every payment its amount in euros at its own day's rate. Euro payments are 1:1. Returns counts: euro, converted, missing (per currency)."""
    from .db import get_setting

    main = get_setting(conn, "currency", "EUR")
    done = {"euro": 0, "converted": 0, "missing": 0}
    for r in conn.execute(
        "SELECT id, day, amount_minor, COALESCE(NULLIF(currency,''), ?) AS cur FROM transactions WHERE eur_minor IS NULL", (main,)
    ).fetchall():
        if r["cur"] == REPORTING:
            conn.execute("UPDATE transactions SET eur_minor=?, rate='1', rate_source='euro' WHERE id=?", (r["amount_minor"], r["id"]))
            done["euro"] += 1
            continue
        found = rate_on(conn, r["cur"], r["day"])
        if found is None:
            done["missing"] += 1
            continue
        per_eur, rate_day = found
        conn.execute(
            "UPDATE transactions SET eur_minor=?, rate=?, rate_source=? WHERE id=?",
            (to_eur(r["amount_minor"], per_eur), str(per_eur), f"ecb {rate_day}", r["id"]),
        )
        done["converted"] += 1
    conn.commit()
    return done
