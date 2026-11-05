"""Finance's view of the shared database: the same storage (kit.db), plus the `ledger` view its reports read."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from kit import db as _kit
from kit.db import EncryptionError, MigrationError, database_key, get_setting, home, rows, set_setting
from kit.module import Module

__all__ = [
    "EncryptionError",
    "MigrationError",
    "connect",
    "database_key",
    "display_currency",
    "get_setting",
    "home",
    "ledger_view",
    "migrate",
    "rows",
    "set_setting",
    "view_currency",
]


def connect(path: str | Path | None = None, key: str | None = None) -> sqlite3.Connection:
    return _kit.connect(path, key, on_open=ledger_view)


def migrate(conn: sqlite3.Connection, modules: list[Module]) -> None:
    _kit.migrate(conn, modules, after=ledger_view)


def ledger_view(conn: sqlite3.Connection) -> None:
    """`ledger` = the payments the reports read. By default ONE currency, shown as it is (the main currency until you pick another), so euros and rupees are
    never added together. 'ALL' is the option to convert everything to euros at the rate of each payment's day. Payments with no currency recorded count as
    the main currency. A per-connection view over `transactions`; every report reads it. `native_minor` is always the amount in the payment's own currency."""
    main = "COALESCE((SELECT value FROM main.settings WHERE key='currency'), 'EUR')"
    viewed = f"COALESCE((SELECT value FROM main.settings WHERE key='view_currency'), {main})"
    try:
        conn.execute("DROP VIEW IF EXISTS temp.ledger")
        columns = [r[1] for r in conn.execute("PRAGMA main.table_info(transactions)")]
        plain = "*, amount_minor AS native_minor"
        if "eur_minor" in columns:
            # 'ALL' = everything in euros at the rate of its own day; a payment that could not be converted is left out and reported, never guessed
            everything = ", ".join("eur_minor AS amount_minor" if c == "amount_minor" else c for c in columns) + ", amount_minor AS native_minor"
            conn.execute(
                f"CREATE TEMP VIEW ledger AS SELECT {everything} FROM main.transactions WHERE {viewed} = 'ALL' AND eur_minor IS NOT NULL "
                f"UNION ALL SELECT {plain} FROM main.transactions WHERE {viewed} = 'ALL' AND eur_minor IS NULL AND COALESCE(NULLIF(currency, ''), {main}) = 'EUR' "
                f"UNION ALL SELECT {plain} FROM main.transactions WHERE {viewed} <> 'ALL' AND COALESCE(NULLIF(currency, ''), {main}) = {viewed}"
            )
        else:
            conn.execute(
                f"CREATE TEMP VIEW ledger AS SELECT {plain} FROM main.transactions WHERE {viewed} <> 'ALL' AND COALESCE(NULLIF(currency, ''), {main}) = {viewed}"
            )
    except sqlite3.Error:
        pass  # before the first migration there is nothing to view


def view_currency(conn: sqlite3.Connection) -> str:
    """One currency, shown as it is (the default: your main currency), or 'ALL' = everything converted to euros."""
    return get_setting(conn, "view_currency", "") or get_setting(conn, "currency", "EUR")


def display_currency(conn: sqlite3.Connection) -> str:
    """The currency the amounts on screen are in."""
    v = view_currency(conn)
    return "EUR" if v == "ALL" else v
