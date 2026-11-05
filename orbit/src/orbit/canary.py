"""The self-test: before and after every import, known sample statements run through the readers and the answers must be exactly right.
If a code change, a library update or a corrupted file ever makes the readers give a different answer, this fails loudly BEFORE any of your numbers are touched."""

from __future__ import annotations

from . import rates, standards, tables
from .verify import Finding

SAMPLE = [
    ["Datum", "Omschrijving", "Af", "Bij", "Saldo"],
    ["01-10-2026", "Opening", "", "", "2.000,00"],
    ["02-10-2026", "Albert Heijn", "23,45", "", "1.976,55"],
    ["25-10-2026", "Salaris", "", "2.850,00", "4.826,55"],
    ["26-10-2026", "Huur", "1.100,00", "", "3.726,55"],
]
COLS = [(0, 60), (70, 200), (210, 260), (270, 320), (330, 400)]


def _layout() -> tables.Layout:
    return tables.Layout(header_line=0, roles=["date", "description", "debit", "credit", "balance"], date_format="%d-%m-%Y", decimal=",", thousands=".")


MT940 = ":20:T\n:25:NL00TEST0000000001\n:60F:C261001EUR100,00\n:61:2610011001D10,00NTRFNONREF\n:86:Shop\n:62F:C261031EUR90,00\n-\n"


def _table(rows):
    return [[tables.Cell(COLS[i][0], COLS[i][1], c) for i, c in enumerate(r) if c != ""] for r in rows]


def run() -> list[Finding]:
    problems: list[str] = []
    want = [("2026-10-02", 2345, "expense"), ("2026-10-25", 285000, "income"), ("2026-10-26", 110000, "expense")]
    p = tables.parse_table(_table(SAMPLE), _layout())
    if p.status != "verified" or sorted((t.day, t.amount_minor, t.kind) for t in p.txns) != want:
        problems.append("a known statement is no longer read exactly")
    rev = tables.parse_table(_table([SAMPLE[0], *SAMPLE[1:][::-1]]), _layout())
    if rev.status != "verified" or len(rev.txns) != 3:
        problems.append("a newest-first statement is no longer read exactly")
    bad = [list(r) for r in SAMPLE]
    bad[3][4] = "4.826,56"
    if tables.parse_table(_table(bad), _layout()).status != "needs_check":
        problems.append("a statement with one wrong cent is no longer caught")
    (s,) = standards.read_mt940(MT940)
    if s.status != "verified" or len(s.txns) != 1 or s.txns[0].amount_minor != 1000:
        problems.append("an MT940 sample is no longer read exactly")
    if tables.money_from_printed("3.500,00") != 350000 or tables.money_from_printed("1,234.56") != 123456:
        problems.append("amounts are no longer read correctly")
    from decimal import Decimal

    if rates.to_eur(900000, Decimal("90.5")) != 9945:
        problems.append("currency conversion no longer gives the right answer")
    if problems:
        return [Finding("self-test", "fail", "readers", "; ".join(problems))]
    return [Finding("self-test", "ok", "readers", "the readers still give the exact right answer on known samples")]
