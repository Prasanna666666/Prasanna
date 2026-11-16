"""Sort transactions into categories. Rules first (instant, free, predictable), your own corrections next, the local model last.

Nothing here uses the network. The local model (when asked) sees only a short merchant name, never amounts or dates, and may only
answer with a category from the fixed list below.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "categories.json").read_text(encoding="utf-8"))
CATEGORIES: tuple[str, ...] = tuple(_DATA["categories"])
# (category, words) from categories.json. A word matches whole-word, case-insensitive. Order matters: the first matching rule wins.
RULES: tuple[tuple[str, tuple[str, ...]], ...] = tuple((r["category"], tuple(r["words"])) for r in _DATA["rules"])
ROUTINE: tuple[str, ...] = tuple(_DATA["routine"])
NOT_INCOME: frozenset[str] = frozenset(_DATA["income_never"])  # money coming in from a shop is a refund, not a purchase
_COMPILED = [(cat, re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(w.strip()) for w in words) + r")(?![a-z0-9])", re.IGNORECASE)) for cat, words in RULES]

_NOISE = re.compile(
    r"\b(upi|imps|neft|rtgs|pos|ach|nach|ecs|atm|ref|txn|payment|paid|to|from|by|via|debit|credit|card|purchase|dr|cr|ib|mb|mobile|"
    r"banking|bank|ltd|pvt|private|limited|india|inr|rs|com|order|ybl|okaxis|okhdfcbank|oksbi|okicici|icici|axl|apl|paytm|ibl|"
    r"hdfcbank|sbi|axis|upiqr)\b",
    re.IGNORECASE,
)


def merchant(desc: str) -> str:
    """A short, stable name for who the money went to or came from: 'UPI-SWIGGY-swiggy@icici-4567' -> 'swiggy'."""
    text = re.sub(r"[@/\\|_\-:*.,()]+", " ", desc.lower())
    text = re.sub(r"\b[a-z]*\d[a-z\d]*\b", " ", text)  # reference numbers, account numbers, ids
    text = _NOISE.sub(" ", text)
    words = list(dict.fromkeys(w for w in text.split() if len(w) > 1))[:3]  # no repeats: 'swiggy swiggy' is one name
    return " ".join(words)


def by_rules(desc: str, kind: str) -> str | None:
    for category, pattern in _COMPILED:
        if pattern.search(desc):
            if kind == "income" and category in NOT_INCOME:
                continue
            return category
    return None


def categorise(desc: str, kind: str, learned: dict[str, str] | None = None) -> str:
    """Your own earlier choice for this merchant wins; then the built-in rules; else 'income'/'other'."""
    m = merchant(desc)
    if learned and m and m in learned:
        return learned[m]
    return by_rules(desc, kind) or ("income" if kind == "income" else "other")


def learned_rules(conn) -> dict[str, str]:
    return {r["merchant"]: r["category"] for r in conn.execute("SELECT merchant, category FROM merchant_rules")}


def teach(conn, desc: str, category: str) -> str:
    """Remember a correction: every transaction from this merchant, now and in future imports, gets this category."""
    category = category.strip().lower()
    m = merchant(desc)
    if not m:
        raise ValueError("this description has no merchant name to learn from")
    conn.execute("INSERT OR REPLACE INTO merchant_rules (merchant, category) VALUES (?,?)", (m, category))
    for r in conn.execute("SELECT id, note FROM transactions WHERE category IN ('other','income') OR auto=1").fetchall():
        if merchant(r["note"]) == m:
            conn.execute("UPDATE transactions SET category=?, auto=0 WHERE id=?", (category, r["id"]))
    conn.commit()
    return m


def model_categories(client, model: str, names: list[str]) -> dict[str, str]:
    """Ask the local model to place merchant names (only names) into the fixed category list."""
    msg = client.chat(
        model,
        [
            {
                "role": "system",
                "content": "Put each merchant into exactly one category from this list: "
                + ", ".join(CATEGORIES)
                + '. Reply with only a JSON object mapping each merchant to its category, e.g. {"swiggy": "food"}. Use "other" if unsure.',
            },
            {"role": "user", "content": json.dumps(names)},
        ],
    )
    m = re.search(r"\{.*\}", msg.get("content") or "", re.DOTALL)
    try:
        found = json.loads(m.group(0)) if m else {}
    except ValueError:
        return {}
    return {k: v.lower() for k, v in found.items() if k in names and isinstance(v, str) and v.lower() in CATEGORIES}


def recategorise_with_model(conn, client, model: str, batch: int = 40) -> int:
    """Use the local model on the merchants the rules could not place. Returns how many transactions were updated."""
    pending: dict[str, list[int]] = {}
    for r in conn.execute("SELECT id, note FROM transactions WHERE category='other' AND auto=1"):
        m = merchant(r["note"])
        if m:
            pending.setdefault(m, []).append(r["id"])
    names = sorted(pending, key=lambda n: -len(pending[n]))[:200]
    updated = 0
    for i in range(0, len(names), batch):
        for name, category in model_categories(client, model, names[i : i + batch]).items():
            if category != "other":
                for tid in pending[name]:
                    conn.execute("UPDATE transactions SET category=? WHERE id=?", (category, tid))
                updated += len(pending[name])
    conn.commit()
    return updated
