"""The verifiers, tested with random statements. Each generated statement must be read back EXACTLY; every alteration of it must be caught."""

import random

import pytest

from orbit import tables
from orbit.statements import Txn

NOTATIONS = [(",", "."), (".", ","), (".", ""), (",", " ")]
COLS5 = [(0, 60), (70, 200), (210, 260), (270, 320), (330, 400)]
COLS4 = [(0, 60), (70, 200), (210, 290), (300, 400)]


def fmt(minor, decimal, thousands):
    whole, cents = divmod(abs(minor), 100)
    digits = f"{whole:,}".replace(",", thousands) if thousands else str(whole)
    return f"{'-' if minor < 0 else ''}{digits}{decimal}{cents:02d}"


def build(rng):
    decimal, thousands = rng.choice(NOTATIONS)
    signed = rng.random() < 0.4  # one signed amount column, or separate money-out / money-in columns
    n = rng.randint(3, 25)
    opening = rng.randint(0, 2_000_000)
    bal, truth, rows = opening, [], []
    f = lambda v: fmt(v, decimal, thousands)  # noqa: E731
    head = ["Datum", "Omschrijving", "Bedrag", "Saldo"] if signed else ["Datum", "Omschrijving", "Af", "Bij", "Saldo"]
    rows.append(["01-10-2026", "Beginsaldo", *([""] * (len(head) - 3)), f(opening)])
    for i in range(n):
        amount = rng.randint(1, 900_000)
        income = rng.random() < 0.35
        bal += amount if income else -amount
        day = f"{2 + i % 27:02d}-10-2026"
        truth.append(Txn(f"2026-10-{2 + i % 27:02d}", amount, "income" if income else "expense", f"Shop {i}", bal))
        if signed:
            rows.append([day, f"Shop {i}", f(amount if income else -amount), f(bal)])
        else:
            rows.append([day, f"Shop {i}", "" if income else f(amount), f(amount) if income else "", f(bal)])
    rows.append(["31-10-2026", "Eindsaldo", *([""] * (len(head) - 3)), f(bal)])
    layout = tables.Layout(0, ["date", "description", "amount", "balance"] if signed else ["date", "description", "debit", "credit", "balance"],
                           "%d-%m-%Y", decimal, thousands)
    return head, rows, truth, layout, COLS4 if signed else COLS5


def table_of(head, rows, cols):
    return [[tables.Cell(cols[i][0], cols[i][1], c) for i, c in enumerate(r) if c != ""] for r in [head, *rows]]


def key(txns):
    return sorted((t.day, t.amount_minor, t.kind) for t in txns)


@pytest.mark.parametrize("seed", range(120))
def test_a_random_statement_is_read_back_exactly_and_proved(seed):
    rng = random.Random(seed)
    head, rows, truth, layout, cols = build(rng)
    p = tables.parse_table(table_of(head, rows, cols), layout)
    assert p.status == "verified", p.issues
    assert key(p.txns) == key(truth)


@pytest.mark.parametrize("seed", range(60))
def test_newest_first_statements_are_read_back_exactly_too(seed):
    rng = random.Random(1000 + seed)
    head, rows, truth, layout, cols = build(rng)
    reversed_rows = rows[::-1]  # opening and closing lines swap places as well, as on a real newest-first statement
    p = tables.parse_table(table_of(head, reversed_rows, cols), layout)
    assert p.status == "verified", p.issues
    assert key(p.txns) == key(truth)


def _mutate(rows, rng, how, signed):
    rows = [list(r) for r in rows]
    body = list(range(1, len(rows) - 1))  # the transaction lines (not opening / closing)
    i = rng.choice(body)
    if how == "drop":
        del rows[i]
    elif how == "duplicate":
        rows.insert(i, list(rows[i]))
    elif how == "balance":
        rows[i][-1] = bump(rows[i][-1])
    elif how == "amount":
        col = 2 if signed else next(c for c in (2, 3) if rows[i][c])
        rows[i][col] = bump(rows[i][col])
    return rows


def bump(text):
    """One cent more (or less), keeping the notation."""
    digits = [i for i, c in enumerate(text) if c.isdigit()]
    last = digits[-1]
    new = str((int(text[last]) + 1) % 10)
    return text[:last] + new + text[last + 1:]


@pytest.mark.parametrize("how", ["drop", "duplicate", "balance", "amount"])
@pytest.mark.parametrize("seed", range(40))
def test_every_alteration_of_a_statement_is_caught(seed, how):
    rng = random.Random(5000 + seed)
    head, rows, truth, layout, cols = build(rng)
    signed = len(head) == 4
    tampered = _mutate(rows, rng, how, signed)
    p = tables.parse_table(table_of(head, tampered, cols), layout)
    assert p.status == "needs_check", f"{how} was not caught"


def test_a_missing_last_line_is_only_caught_because_the_closing_balance_is_printed():
    """Honest limit, written down as a test: without a printed closing balance the running balances cannot reveal that the LAST line is missing."""
    rng = random.Random(7)
    head, rows, truth, layout, cols = build(rng)
    without_closing = rows[:-2]  # the last transaction and the closing balance line are both gone
    p = tables.parse_table(table_of(head, without_closing, cols), layout)
    assert p.status == "verified"  # nothing contradicts it: the next statement's opening balance (continuity) is what would catch this
