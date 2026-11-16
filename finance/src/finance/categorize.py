"""Sort transactions into categories. Your own corrections first, then what the local model decided about the merchant (once: the answer is remembered), else 'other'.

Nothing here uses the network. The local model sees only a short merchant name, never amounts or dates, and may only answer with a category from
`categories.json`, where each category has a plain description. There are no merchant or word lists: a new merchant needs no edit anywhere.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_DATA = json.loads((Path(__file__).parent / "categories.json").read_text(encoding="utf-8"))
CATEGORY_ABOUT: dict[str, str] = {c["name"]: c["about"] for c in _DATA["categories"]}
CATEGORIES: tuple[str, ...] = tuple(CATEGORY_ABOUT)
ROUTINE: tuple[str, ...] = tuple(_DATA["routine"])
NOT_INCOME: frozenset[str] = frozenset(_DATA["income_never"])  # money coming in from a shop is a refund, not a purchase
MERCHANTS_PER_ASK = 40  # merchant names put to the model in one question
MERCHANTS_PER_RUN = 200  # the most merchants decided in one run, commonest first; the rest wait for the next


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


def categorise(desc: str, kind: str, learned: dict[str, str] | None = None, decided: dict[str, str] | None = None) -> str:
    """Your own earlier choice for this merchant wins; then what the model decided about it; else 'income' or 'other' until the model has been asked."""
    m = merchant(desc)
    if learned and m and m in learned:
        return learned[m]
    found = decided.get(m) if decided and m else None
    if found and not (kind == "income" and found in NOT_INCOME):
        return found
    return "income" if kind == "income" else "other"


def learned_rules(conn) -> dict[str, str]:
    """The person's own corrections: merchant -> category."""
    return {r["merchant"]: r["category"] for r in conn.execute("SELECT merchant, category FROM merchant_rules")}


def model_decisions(conn) -> dict[str, str]:
    """What the model decided about each merchant it was asked about: merchant -> category."""
    return {r["merchant"]: r["category"] for r in conn.execute("SELECT merchant, category FROM merchant_categories")}


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
    """Ask the local model to place merchant names (only names) into the category list, each with its plain description."""
    listed = "\n".join(f"- {name}: {about}" for name, about in CATEGORY_ABOUT.items())
    msg = client.chat(
        model,
        [
            {
                "role": "system",
                "content": "Put each merchant into exactly one of these categories:\n"
                + listed
                + '\nReply with only a JSON object mapping each merchant to its category, e.g. {"some shop": "shopping"}. Use "other" if unsure.',
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


def recategorise_with_model(conn, client, model: str, batch: int = MERCHANTS_PER_ASK) -> int:
    """Ask the local model about every merchant nobody has decided yet (once each: the answer is remembered), and give its payments that category.
    Returns how many transactions were updated."""
    asked = set(model_decisions(conn)) | set(learned_rules(conn))
    pending: dict[str, int] = {}
    for r in conn.execute("SELECT note FROM transactions WHERE category IN ('other','income') AND auto=1"):
        m = merchant(r["note"])
        if m and m not in asked:
            pending[m] = pending.get(m, 0) + 1
    names = sorted(pending, key=lambda n: -pending[n])[:MERCHANTS_PER_RUN]
    for i in range(0, len(names), batch):
        for name, category in model_categories(client, model, names[i : i + batch]).items():
            conn.execute("INSERT OR REPLACE INTO merchant_categories (merchant, category) VALUES (?,?)", (name, category))
    conn.commit()
    return apply_decisions(conn)


def apply_decisions(conn) -> int:
    """Give every automatically sorted payment the category the model decided for its merchant (never against the person's own corrections)."""
    decided, corrected = model_decisions(conn), learned_rules(conn)
    updated = 0
    for r in conn.execute("SELECT id, note, kind FROM transactions WHERE category IN ('other','income') AND auto=1").fetchall():
        m = merchant(r["note"])
        category = decided.get(m) if m not in corrected else None
        if category and category != "other" and not (r["kind"] == "income" and category in NOT_INCOME):
            conn.execute("UPDATE transactions SET category=? WHERE id=?", (category, r["id"]))
            updated += 1
    conn.commit()
    return updated
