"""Exact Finance calculations by code (Stage 5; G-021: the local model may read authorised Finance data, but every figure it is given or may state is computed and checked here, never by the model).

All money is `Decimal` with two places (no float anywhere). Every aggregate is computed twice by independent routes (Decimal sums, and integer minor units) and `summary_records` refuses to emit a
figure when the two disagree. A summary is itself a Finance record whose note lists the ids of every input, so a citation of it leads to its inputs, and `verify_summary` recomputes it from them.
Percentages are rounded half-up to one place and labelled as rounded; they are never presented as exact. Nothing here moves money or reaches a network.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .records import Record
from .rules import load_rules

DAY_LENGTH = 10
MONEY_DOMAIN = next(
    name for name, schema in load_rules().raw["records"].items() if schema.get("money")
)  # the one domain whose records carry money: named by the policy data, not here
CENT = Decimal("0.01")
ONE_PLACE = Decimal("0.1")
SUMMARY_PREFIX = "sum-"


class CalcError(ValueError):
    """A calculation that cannot be trusted. Carries a code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Tx:
    record_id: str
    day: str  # YYYY-MM-DD
    amount: Decimal
    kind: str  # expense | income
    category: str
    merchant: str
    currency: str = ""  # ISO 4217; amounts of different currencies are never added together

    @property
    def month(self) -> str:
        return self.day[:7]

    @property
    def minor(self) -> int:
        return int(self.amount * 100)


def transactions(records: Iterable[Record]) -> list[Tx]:
    out = []
    for r in records:
        if r.domain != MONEY_DOMAIN or r.record_id.startswith(SUMMARY_PREFIX):
            continue  # a summary is derived: it never feeds another summary
        day = r.date[:10]
        if len(day) != DAY_LENGTH or day[4] != "-" or day[7] != "-":
            raise CalcError("bad_date")
        out.append(
            Tx(
                r.record_id,
                day,
                Decimal(r.fields["amount"]),
                r.fields["kind"],
                r.fields.get("category", "uncategorised") or "uncategorised",
                r.fields.get("merchant", ""),
                r.fields.get("currency", ""),
            )
        )
    return out


def _decimal_sum(values: Iterable[Decimal]) -> Decimal:
    total = Decimal("0.00")
    for v in values:
        total += v
    return total.quantize(CENT)


def _minor_sum(values: Iterable[int]) -> Decimal:
    return (Decimal(sum(values)) / 100).quantize(CENT)


def total(txs: Iterable[Tx]) -> Decimal:
    """The sum of the amounts, computed by two routes that must agree."""
    items = list(txs)
    if len({t.currency for t in items}) > 1:
        raise CalcError("mixed_currency")  # no sum, share or percentage across currencies without an explicit, sourced conversion (there is none)
    by_decimal, by_minor = _decimal_sum(t.amount for t in items), _minor_sum(t.minor for t in items)
    if by_decimal != by_minor:
        raise CalcError("sums_disagree")
    return by_decimal


def by_month(txs: Iterable[Tx], kind: str = "expense") -> dict[str, Decimal]:
    groups: dict[str, list[Tx]] = defaultdict(list)
    for t in txs:
        if t.kind == kind:
            groups[t.month].append(t)
    return {m: total(v) for m, v in sorted(groups.items())}


def by_category(txs: Iterable[Tx], month: str, kind: str = "expense") -> dict[str, Decimal]:
    groups: dict[str, list[Tx]] = defaultdict(list)
    for t in txs:
        if t.kind == kind and t.month == month:
            groups[t.category].append(t)
    return {c: total(v) for c, v in sorted(groups.items())}


def previous_month(month: str) -> str:
    year, m = int(month[:4]), int(month[5:7])
    return f"{year - 1}-12" if m == 1 else f"{year}-{m - 1:02d}"


@dataclass(frozen=True)
class Change:
    previous: Decimal
    current: Decimal
    delta: Decimal  # exact
    percent: Decimal | None  # rounded half-up to one place; None when the previous month was zero (no percentage exists)


def month_over_month(txs: Iterable[Tx], month: str, category: str | None = None, kind: str = "expense") -> Change:
    items = [t for t in txs if t.kind == kind and (category is None or t.category == category)]
    now, before = total(t for t in items if t.month == month), total(t for t in items if t.month == previous_month(month))
    delta = (now - before).quantize(CENT)
    percent = None if before == 0 else (delta / before * 100).quantize(ONE_PLACE, rounding=ROUND_HALF_UP)
    return Change(before, now, delta, percent)


def recurring(txs: Iterable[Tx], min_months: int = 3) -> list[tuple[str, Decimal, list[str]]]:
    """Charges from the same merchant for the same amount in at least `min_months` CONSECUTIVE months, oldest month first."""
    seen: dict[tuple[str, Decimal], set[str]] = defaultdict(set)
    for t in txs:
        if t.kind == "expense" and t.merchant:
            seen[(t.merchant, t.amount)].add(t.month)
    found = []
    for (merchant, amount), months in sorted(seen.items()):
        run: list[str] = []
        best: list[str] = []
        for m in sorted(months):
            run = [*run, m] if run and previous_month(m) == run[-1] else [m]
            best = run if len(run) > len(best) else best
        if len(best) >= min_months:
            found.append((merchant, amount, best))
    return found


def budget_variance(txs: Iterable[Tx], month: str, budgets: Mapping[str, Decimal]) -> dict[str, tuple[Decimal, Decimal, Decimal]]:
    """Per budgeted category: (spent, budget, variance = budget - spent). Positive variance means under budget."""
    spent = by_category(txs, month)
    return {c: (spent.get(c, Decimal("0.00")), b, (b - spent.get(c, Decimal("0.00"))).quantize(CENT)) for c, b in sorted(budgets.items())}


def cash_flow(txs: Iterable[Tx], month: str) -> tuple[Decimal, Decimal, Decimal]:
    items = list(txs)
    income, expense = by_month(items, "income").get(month, Decimal("0.00")), by_month(items, "expense").get(month, Decimal("0.00"))
    return income, expense, (income - expense).quantize(CENT)


def currencies(txs: Iterable[Tx]) -> list[str]:
    return sorted({t.currency for t in txs})


def only(txs: Iterable[Tx], currency: str) -> list[Tx]:
    """The transactions in one currency: the way to ask any aggregate question of mixed data."""
    return [t for t in txs if t.currency == currency]


def summary_records(records: Iterable[Record]) -> list[Record]:
    """Per currency, month and category: one Finance record stating the exact total in THAT currency, with the ids of every input, so a citation of the total leads to the transactions it is made of. A
    currency is never assumed or relabelled. The legacy id (no suffix) is kept for EUR; any other currency adds its code to the id."""
    items = [r for r in records if r.domain == MONEY_DOMAIN and not r.record_id.startswith(SUMMARY_PREFIX)]
    txs = transactions(items)
    inputs: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for t in txs:
        if t.kind == "expense":
            inputs[(t.currency, t.month, t.category)].append(t.record_id)
    out = []
    for currency, month in sorted({(c, m) for c, m, _ in inputs}):
        for category, amount in by_category(only(txs, currency), month).items():
            ids = sorted(inputs[(currency, month, category)])
            suffix = "" if currency == "EUR" else f"-{currency}"
            out.append(
                Record(
                    f"{SUMMARY_PREFIX}{month}-{category}{suffix}".replace(" ", "-"),
                    MONEY_DOMAIN,
                    f"{month}-28",
                    f"Total {category} {month}",
                    {
                        "amount": str(amount),
                        "currency": currency,
                        "kind": "expense",
                        "category": category,
                        "note": f"computed by code from {len(ids)} transactions: {', '.join(ids)}",
                    },
                )
            )
    return out


def verify_summary(summary: Record, records: Iterable[Record]) -> bool:
    """Recompute a summary from the transactions it names and compare. False means the figure must not be shown."""
    note = summary.fields.get("note", "")
    if not summary.record_id.startswith(SUMMARY_PREFIX) or "computed by code from" not in note:
        return False
    named = [s.strip() for s in note.split(":", 1)[1].split(",")]
    index = {t.record_id: t for t in transactions(records)}
    if any(i not in index for i in named):
        return False
    month, category = summary.date[:7], summary.fields.get("category", "")
    parts = [index[i] for i in named]
    if any(t.month != month or t.category != category or t.kind != "expense" or t.currency != summary.fields.get("currency", "") for t in parts):
        return False
    return total(parts) == Decimal(summary.fields["amount"])
