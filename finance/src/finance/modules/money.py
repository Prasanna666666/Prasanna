"""Income, expenses and monthly category budgets. Amounts are stored as integer minor units (paise/cents)."""

from __future__ import annotations

from datetime import date, timedelta

from kit import money as kit_money
from kit.module import INT, Module, N, S, Tool

from .. import (
    audit,
    browse,
    categorize,
    clock,
    concepts,
    dates,
    insight,
    planning,
    proof,
    wealth,
)
from ..db import get_setting, rows
from . import reports, statement_import

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
    """
    ALTER TABLE transactions ADD COLUMN ref TEXT;                          -- stable id of an imported line: the same line is never added twice
    ALTER TABLE transactions ADD COLUMN source TEXT NOT NULL DEFAULT '';   -- the statement it came from
    ALTER TABLE transactions ADD COLUMN balance_minor INTEGER;
    ALTER TABLE transactions ADD COLUMN auto INTEGER NOT NULL DEFAULT 0;   -- 1 = category chosen by rules/model, 0 = chosen by you
    CREATE UNIQUE INDEX tx_ref ON transactions(ref) WHERE ref IS NOT NULL;
    CREATE TABLE merchant_rules (merchant TEXT PRIMARY KEY, category TEXT NOT NULL);
    CREATE TABLE payslips (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, period TEXT NOT NULL, gross_minor INTEGER NOT NULL, net_minor INTEGER NOT NULL,
        tax_minor INTEGER, pension_minor INTEGER, holiday_minor INTEGER
    );
    CREATE TABLE statement_files (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, found INTEGER NOT NULL, added INTEGER NOT NULL,
        at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    -- what the model read from every finance file: invoices, receipts, tax, insurance ... (a new step: existing databases get it too)
    CREATE TABLE IF NOT EXISTS finance_docs (
        sha256 TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
        party TEXT NOT NULL DEFAULT '', doc_date TEXT, due_date TEXT, reference TEXT NOT NULL DEFAULT '',
        total_minor INTEGER, vat_minor INTEGER, currency TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS finance_docs_kind ON finance_docs(kind, doc_date);
    """,
    """
    ALTER TABLE statement_files ADD COLUMN status TEXT NOT NULL DEFAULT 'ok';      -- verified | unverified | needs_check | ok (not a statement)
    ALTER TABLE statement_files ADD COLUMN issues TEXT NOT NULL DEFAULT '';        -- why a file needs a check
    """,
    """
    ALTER TABLE statement_files ADD COLUMN account TEXT NOT NULL DEFAULT '';       -- the account/card number printed on the statement
    ALTER TABLE statement_files ADD COLUMN period_start TEXT;
    ALTER TABLE statement_files ADD COLUMN period_end TEXT;
    ALTER TABLE statement_files ADD COLUMN opening_minor INTEGER;
    ALTER TABLE statement_files ADD COLUMN closing_minor INTEGER;
    ALTER TABLE statement_files ADD COLUMN proofs TEXT NOT NULL DEFAULT '';        -- how it was proved
    CREATE TABLE findings (                                                        -- what each verifier agent concluded
        id INTEGER PRIMARY KEY, agent TEXT NOT NULL, level TEXT NOT NULL CHECK (level IN ('ok','warn','fail')),
        subject TEXT NOT NULL, message TEXT NOT NULL, cross INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    ALTER TABLE transactions ADD COLUMN currency TEXT NOT NULL DEFAULT '';        -- '' = the main currency
    ALTER TABLE transactions ADD COLUMN account TEXT NOT NULL DEFAULT '';         -- the account/card the payment belongs to, as printed on its statement
    ALTER TABLE transactions ADD COLUMN transfer_id INTEGER;                      -- the other half of a transfer between your own accounts
    ALTER TABLE statement_files ADD COLUMN currency TEXT NOT NULL DEFAULT '';
    CREATE INDEX tx_account ON transactions(account, day);
    """,
    """
    ALTER TABLE transactions ADD COLUMN eur_minor INTEGER;                        -- the amount in euros at the rate of its own day (NULL = not converted yet)
    ALTER TABLE transactions ADD COLUMN rate TEXT NOT NULL DEFAULT '';            -- units of the payment's currency per 1 EUR that were used
    ALTER TABLE transactions ADD COLUMN rate_source TEXT NOT NULL DEFAULT '';     -- 'euro' | 'ecb <day>' | 'transfer'
    CREATE TABLE rates (day TEXT NOT NULL, currency TEXT NOT NULL, per_eur TEXT NOT NULL, PRIMARY KEY (day, currency));
    """,
    """
    ALTER TABLE finance_docs ADD COLUMN gross_minor INTEGER;                      -- payslips and annual statements: the figures as verified against the text
    ALTER TABLE finance_docs ADD COLUMN tax_minor INTEGER;
    ALTER TABLE finance_docs ADD COLUMN net_minor INTEGER;
    ALTER TABLE finance_docs ADD COLUMN period TEXT NOT NULL DEFAULT '';
    ALTER TABLE transactions ADD COLUMN refund_of INTEGER;                        -- the purchase a refund gives money back for
    CREATE TABLE merchant_alias (alias TEXT PRIMARY KEY, canonical TEXT NOT NULL); -- 'ah 1234' and 'albert heijn' are one shop
    CREATE TABLE audit_log (                                                      -- every import and correction, each entry sealed with the one before
        id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL
    );
    """,
    """
    -- speed: the reports and the agents look payments up by month, account and amount
    CREATE INDEX IF NOT EXISTS tx_day ON transactions(day);
    CREATE INDEX IF NOT EXISTS tx_acc_amount ON transactions(account, amount_minor, day);
    CREATE INDEX IF NOT EXISTS tx_refund ON transactions(refund_of) WHERE refund_of IS NOT NULL;
    """,
    """
    CREATE TABLE IF NOT EXISTS goals (                                           -- something you are saving for
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, target_minor INTEGER NOT NULL, by_date TEXT, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS holdings (                                        -- what you typed in: investments, assets (house, car), debts (loan, mortgage)
        id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('investment','asset','debt')),
        value_minor INTEGER NOT NULL, units REAL, price_minor INTEGER, currency TEXT NOT NULL DEFAULT 'EUR', as_of TEXT NOT NULL
    );
    """,
    """
    ALTER TABLE holdings ADD COLUMN cost_minor INTEGER;                          -- what you paid in for it in total, so a gain or loss can be shown
    """,
    """
    ALTER TABLE finance_docs ADD COLUMN start_date TEXT;                         -- a ticket or booking: departure or check-in (written in the document)
    ALTER TABLE finance_docs ADD COLUMN end_date TEXT;
    ALTER TABLE finance_docs ADD COLUMN place TEXT NOT NULL DEFAULT '';          -- where to
    CREATE TABLE IF NOT EXISTS mail_skipped (sha256 TEXT PRIMARY KEY);           -- mail documents not worth asking the model about, so they are judged once
    """,
    """
    ALTER TABLE finance_docs ADD COLUMN concept TEXT NOT NULL DEFAULT '';        -- what the kind means to Finance (see concepts.py): the queries ask for this, not for the model's words
    CREATE INDEX IF NOT EXISTS finance_docs_concept ON finance_docs(concept, doc_date);
    CREATE TABLE IF NOT EXISTS kind_concepts (kind TEXT PRIMARY KEY, concept TEXT NOT NULL);
    """,
    """
    CREATE TABLE IF NOT EXISTS merchant_categories (merchant TEXT PRIMARY KEY, category TEXT NOT NULL);  -- what the model decided about each merchant, once
    """,
    """
    CREATE TABLE IF NOT EXISTS assistant_changes (   -- changes the assistant proposed to the money records, and what became of each (the audit trail)
        id INTEGER PRIMARY KEY,
        tool TEXT NOT NULL,
        args TEXT NOT NULL,
        summary TEXT NOT NULL,
        turn TEXT NOT NULL,                          -- the question it was prepared in: it cannot be confirmed in the same one
        asked TEXT NOT NULL DEFAULT '',              -- the person's own words when it was prepared
        created TEXT NOT NULL,
        decided TEXT,
        state TEXT NOT NULL DEFAULT 'waiting',       -- waiting, running, done, failed, superseded, expired
        outcome TEXT NOT NULL DEFAULT ''
    );
    CREATE INDEX IF NOT EXISTS assistant_changes_state ON assistant_changes(state, id);
    """,
)


def to_minor(x: object) -> int:
    return kit_money.to_minor(x)


def currency(conn) -> str:
    return get_setting(conn, "currency", "EUR")


def add_transaction(conn, a):
    kit_money.check_fits(a["amount"], currency(conn))
    amt = to_minor(a["amount"])
    if amt <= 0:
        raise ValueError("amount must be positive")
    day = a.get("date") or clock.today().isoformat()
    dates.parse(day)
    cur = conn.execute(
        "INSERT INTO transactions (day, amount_minor, kind, category, note) VALUES (?,?,?,?,?)",
        (day, amt, a.get("kind", "expense"), a.get("category", "other").strip().lower(), a.get("note", "")),
    )
    conn.commit()
    return {"id": cur.lastrowid, "amount": amt / 100, "currency": currency(conn), "date": day}


def list_transactions(conn, a):
    where, args = [], []
    for col, op, key in (("t.day", ">=", "since"), ("t.day", "<=", "until")):
        if a.get(key):
            where.append(f"{col} {op} ?")
            args.append(a[key])
    if a.get("category"):
        where.append("t.category=?")
        args.append(a["category"].lower())
    if a.get("query"):
        where.append("t.note LIKE ?")
        args.append("%" + str(a["query"]).replace("%", "").replace("_", "") + "%")
    for col, op, key in (("t.amount_minor", ">=", "min_amount"), ("t.amount_minor", "<=", "max_amount")):
        if a.get(key) is not None:
            where.append(f"{col} {op} ?")
            args.append(kit_money.to_minor(a[key]))
    sql = (
        "SELECT t.id, t.day, t.kind, t.category, t.note, t.amount_minor/100.0 AS amount, t.native_minor/100.0 AS original, "
        "COALESCE(NULLIF(t.currency,''), (SELECT COALESCE((SELECT value FROM settings WHERE key='currency'),'EUR'))) AS currency, t.event_id, t.sub, e.name AS event "
        "FROM ledger t LEFT JOIN events e ON e.id=t.event_id"
    )
    sql += " WHERE " + " AND ".join(where) if where else ""
    return rows(conn.execute(sql + " ORDER BY t.day DESC, t.id DESC LIMIT ?", [*args, int(a.get("limit", 50))]))


def payment_items(conn, days: int = 400):
    """The payments of the last `days` days as plain dated items (when, how much, to whom), for Atlas to join with what the documents say: a bill and the payment that settled it,
    a trip and what it cost. Only Atlas receives them, and it never passes the bank text on."""
    since = (clock.today() - timedelta(days=days)).isoformat()
    return [
        {
            "src": "finance",
            "kind": "payment",
            "date": r["day"],
            "amount": r["amount_minor"] / 100,
            "currency": r["currency"] or currency(conn),
            "text": str(r["note"] or "")[:200],
            "direction": r["kind"],
        }
        for r in conn.execute(
            "SELECT day, note, amount_minor, kind, currency FROM transactions WHERE day>=? AND category<>'transfers' ORDER BY day DESC LIMIT 5000", (since,)
        )
    ]


def spending_between(conn, a):
    """What was spent in a window of days (inclusive), such as a trip: the total, per category, and the biggest payments. Transfers between your
    own accounts are left out. The window is never guessed: both dates are required."""
    try:
        start, end = date.fromisoformat(str(a["from"])), date.fromisoformat(str(a["to"]))
    except (KeyError, ValueError) as exc:
        raise ValueError("both 'from' and 'to' are needed, as YYYY-MM-DD") from exc
    first, last = start.isoformat(), (end + timedelta(days=1)).isoformat()
    where = "kind='expense' AND category<>'transfers' AND day>=? AND day<?"
    by_cat = rows(
        conn.execute(f"SELECT category, SUM(amount_minor)/100.0 AS spent FROM ledger WHERE {where} GROUP BY category ORDER BY spent DESC", (first, last))
    )
    biggest = rows(
        conn.execute(f"SELECT day, note, amount_minor/100.0 AS amount, category FROM ledger WHERE {where} ORDER BY amount_minor DESC LIMIT 8", (first, last))
    )
    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "currency": currency(conn),
        "spent": sum(r["spent"] for r in by_cat),
        "payments": conn.execute(f"SELECT COUNT(*) FROM ledger WHERE {where}", (first, last)).fetchone()[0],
        "by_category": by_cat,
        "biggest": biggest,
    }


def summary(conn, a):
    start, end = dates.month_bounds(a.get("month") or clock.today().strftime("%Y-%m"))
    by_cat = rows(
        conn.execute(
            "SELECT category, SUM(amount_minor)/100.0 AS spent FROM ledger "
            "WHERE kind='expense' AND category<>'transfers' AND day>=? AND day<? GROUP BY category ORDER BY spent DESC",
            (start, end),
        )
    )
    tot = {
        r["kind"]: r["t"]
        for r in conn.execute(
            "SELECT kind, SUM(amount_minor)/100.0 AS t FROM ledger WHERE category<>'transfers' AND NOT (kind='income' AND event_id IS NOT NULL) "
            "AND day>=? AND day<? GROUP BY kind",
            (start, end),
        )
    }
    budgets = {r["category"]: r["monthly_minor"] / 100 for r in conn.execute("SELECT * FROM budgets")}
    for r in by_cat:
        if r["category"] in budgets:
            r["budget"], r["left"] = budgets[r["category"]], budgets[r["category"]] - r["spent"]
    return {
        "month": start[:7],
        "currency": currency(conn),
        "spent": tot.get("expense", 0),
        "income": tot.get("income", 0),
        "net": tot.get("income", 0) - tot.get("expense", 0),
        "by_category": by_cat,
    }


INCOME_NAMES = {"income": "other income", "refund": "refunds", "interest": "interest"}


def income_summary(conn, a=None):
    """Money in for a month, by source (salary, interest, refunds, other), with the month before and the payslip figures if there is one.
    Refunds that belong to a trip or event are not income: they are netted inside that event."""
    from datetime import date

    a = a or {}
    month = a.get("month") or clock.today().strftime("%Y-%m")
    start, end = dates.month_bounds(month)
    before_start = dates.add_months(date.fromisoformat(start), -1).isoformat()

    def by_source(lo, hi):
        out: dict[str, list] = {}
        for r in conn.execute(
            "SELECT category, note, amount_minor FROM ledger WHERE kind='income' AND event_id IS NULL AND category<>'transfers' AND day>=? AND day<?", (lo, hi)
        ):
            name = INCOME_NAMES.get(
                r["category"], r["category"]
            )  # salary stays 'salary': its description carries the month, so it would never match last month's
            slot = out.setdefault(name, [0, 0])
            slot[0] += r["amount_minor"]
            slot[1] += 1
        return out

    now, before = by_source(start, end), by_source(before_start, start)
    sources = sorted(
        ({"source": k, "amount": v[0] / 100, "payments": v[1], "before": before.get(k, [0])[0] / 100} for k, v in now.items()), key=lambda x: -x["amount"]
    )
    slip = conn.execute(
        "SELECT period, gross_minor/100.0 AS gross, tax_minor/100.0 AS tax, pension_minor/100.0 AS pension, holiday_minor/100.0 AS holiday, net_minor/100.0 AS net "
        "FROM payslips WHERE period=? ORDER BY name LIMIT 1",
        (month,),
    ).fetchone()
    return {
        "month": month,
        "total": round(sum(s["amount"] for s in sources), 2),
        "before": round(sum(v[0] for v in before.values()) / 100, 2),
        "sources": sources,
        "payslip": dict(slip) if slip else None,
    }


def set_budget(conn, a):
    conn.execute("INSERT OR REPLACE INTO budgets VALUES (?,?)", (a["category"].strip().lower(), to_minor(a["monthly_amount"])))
    conn.commit()
    return {"category": a["category"].lower(), "monthly_amount": a["monthly_amount"]}


def delete_transaction(conn, a):
    audit.record(conn, "payment deleted", f"id {a['id']}")
    conn.execute("DELETE FROM transactions WHERE id=?", (a["id"],))
    conn.commit()
    return {"deleted": a["id"]}


MODULE = Module(
    "money",
    MIGRATIONS,
    (
        Tool(
            "add_transaction",
            "Record an expense (default) or income. Amount is positive, in the user's currency.",
            {
                "amount": N("Positive amount"),
                "kind": S("expense or income", enum=["expense", "income"]),
                "category": S("e.g. groceries, rent, medical, travel, salary"),
                "note": S("What it was for"),
                "date": S("YYYY-MM-DD, default today"),
            },
            add_transaction,
            ("amount",),
        ),
        Tool(
            "list_transactions",
            "List transactions, newest first.",
            {
                "since": S("YYYY-MM-DD"),
                "until": S("YYYY-MM-DD"),
                "category": S("Category"),
                "query": S("Words in the description"),
                "min_amount": N("At least this much"),
                "max_amount": N("At most this much"),
                "limit": N("Max rows"),
            },
            list_transactions,
        ),
        Tool(
            "spending_between",
            "What was spent between two dates (inclusive), for example during a trip: total, per category and the biggest payments. Use it whenever a period other than a whole month is asked about.",
            {"from": S("First day, YYYY-MM-DD"), "to": S("Last day, YYYY-MM-DD")},
            spending_between,
            ("from", "to"),
        ),
        Tool(
            "spending_summary",
            "Totals for a month: spent, income, net and per-category spend vs budget.",
            {"month": S("YYYY-MM, default current month")},
            summary,
        ),
        Tool(
            "set_budget",
            "Set a monthly budget for a category.",
            {"category": S("Category"), "monthly_amount": N("Amount per month")},
            set_budget,
            ("category", "monthly_amount"),
        ),
        Tool(
            "import_statements",
            "Import new bank/UPI/card statements from the finance folder into transactions (safe to repeat).",
            {},
            statement_import.import_statements,
        ),
        Tool(
            "finance_documents",
            "Find invoices, receipts, tax letters, insurance, contracts and other finance files, with who/when/how much. "
            "Filter by kind, party (who it is from) and dates.",
            {
                "kind": S("what the file is, in a word or two (" + ", ".join(concepts.CONCEPTS) + ")"),
                "party": S("Name, or part of it"),
                "since": S("YYYY-MM-DD"),
                "until": S("YYYY-MM-DD"),
                "limit": N("Max rows"),
                "documents_only": {"type": "boolean", "description": "true: leave out the emails themselves"},
            },
            statement_import.finance_documents,
        ),
        Tool(
            "finance_document_totals",
            "Add up invoices, receipts, insurance ... by kind, month or who they are from.",
            {"by": S("kind, month or party", enum=["kind", "month", "party"]), "kind": S("Only this kind"), "since": S("YYYY-MM-DD"), "until": S("YYYY-MM-DD")},
            statement_import.finance_document_totals,
        ),
        Tool("currencies", "The currencies in the ledger and which one the totals are showing.", {}, reports.currencies),
        Tool(
            "upcoming_payments",
            "The regular payments coming up (subscriptions, rent, bills): who, how much, and when.",
            {"days": N("How many days ahead, default 35")},
            insight.upcoming_payments,
        ),
        Tool(
            "month_breakdown",
            "Where a month's spending comes from: by file, trips and events apart, the biggest payments, and anything that looks like it is not really spending.",
            {"month": S("YYYY-MM, default the newest month")},
            insight.month_breakdown,
        ),
        Tool(
            "month_proof",
            "Whether a month is PROVEN (every statement checked, balances join up, reports equal the ledger) or not, with each reason.",
            {"month": S("YYYY-MM, default the newest month")},
            proof.month_proof,
        ),
        Tool("wealth_summary", "Net worth: accounts (proven statements) plus investments and assets, minus debts (typed by you).", {}, wealth.wealth_summary),
        Tool("accounts_overview", "Each account with its balance from the latest proven statement.", {}, wealth.accounts_overview),
        Tool("list_holdings", "What you typed in: investments, assets and debts.", {}, wealth.list_holdings),
        Tool(
            "add_holding",
            "Add an investment (units and price), an asset (house, car) or a debt (loan, mortgage).",
            {
                "name": S("Name"),
                "kind": S("investment, asset or debt"),
                "value": N("Value (or units and price)"),
                "units": N("Units held"),
                "price": N("Price per unit"),
                "currency": S("Currency, default the main one"),
                "as_of": S("Date YYYY-MM-DD"),
            },
            wealth.add_holding,
            ("name", "kind"),
        ),
        Tool(
            "update_holding",
            "Give an entered holding a new value or price.",
            {"id": INT("Holding id"), "value": N("New value"), "units": N("Units"), "price": N("New price per unit"), "as_of": S("Date YYYY-MM-DD")},
            wealth.update_holding,
            ("id",),
        ),
        Tool("delete_holding", "Remove an entered holding.", {"id": INT("Holding id")}, wealth.delete_holding, ("id",)),
        Tool(
            "budget_progress",
            "Each monthly budget against what was spent in that category this month.",
            {"month": S("YYYY-MM, default the newest month")},
            planning.budget_progress,
        ),
        Tool("bills_due", "Bills and regular payments coming up: what, how much, when.", {"days": INT("How many days ahead, default 45")}, planning.bills_due),
        Tool(
            "tax_summary",
            "The facts a tax return asks for, for one year, from your documents and statements. Not tax advice.",
            {"year": S("YYYY, default the newest year")},
            planning.tax_summary,
        ),
        Tool(
            "merchant_history",
            "One shop or payee over time: total, per month, latest payments.",
            {"merchant": S("Name or part of it")},
            planning.merchant_history,
            ("merchant",),
        ),
        Tool(
            "explore_payments",
            "Browse payments by filter, with the totals of the whole selection.",
            {
                "month": S("YYYY-MM"),
                "year": S("YYYY"),
                "category": S("Category"),
                "kind": S("expense or income"),
                "query": S("Words"),
                "event": S("Event name"),
                "min_amount": N("At least"),
                "max_amount": N("At most"),
                "sort": S("date or amount"),
                "limit": INT("Rows, default 40"),
                "offset": INT("Skip this many"),
            },
            browse.explore_payments,
        ),
        Tool("payment_detail", "Everything known about one payment: file, account, group, refunds.", {"id": INT("Payment id")}, browse.payment_detail, ("id",)),
        Tool(
            "search_everything",
            "Search payments, shops, documents, people, notes and tasks at once.",
            {"query": S("Words to look for")},
            browse.search_all,
            ("query",),
        ),
        Tool("family_money", "Money between you and each person on your People list, where their name is printed on the payment.", {}, planning.family_money),
        Tool("income_breakdown", "Money in by month and year: salary, bonus and other.", {}, planning.income_breakdown),
        Tool(
            "check_totals",
            "A check of the money-in and money-out figures: months without a statement per account, what each category adds up to, what was left out as transfers or refunds, and warnings.",
            {},
            planning.totals_check,
        ),
        Tool("savings_overview", "What was saved (money in minus spent) and the savings rate, by month and year.", {}, planning.savings_overview),
        Tool("investments_overview", "Investments: what was paid in, the current value you entered, and the gain or loss.", {}, wealth.investments_overview),
        Tool("yearly_overview", "Per year: salary, money in, spent, saved, savings rate, interest, invested, insurance paid.", {}, planning.yearly_overview),
        Tool("interest_earned", "Interest received per year and the estimated yearly rate for each account that earns it.", {}, planning.interest),
        Tool("investments", "What was paid into investments each year. The portfolio value needs broker statements.", {}, planning.investments),
        Tool("insurances", "Each insurance: what the documents say it costs and what was paid per year.", {}, planning.insurances),
        Tool(
            "add_goal",
            "Add something to save for.",
            {"name": S("What it is for"), "target": N("Amount to reach"), "by": S("Date YYYY-MM-DD, optional")},
            planning.add_goal,
            ("name", "target"),
        ),
        Tool("list_goals", "Your savings goals with progress and whether you are on track.", {}, planning.list_goals),
        Tool("delete_goal", "Remove a goal.", {"id": INT("Goal id")}, planning.delete_goal, ("id",)),
        Tool("forecast", "An estimate of the next months from your last six months.", {"months": INT("How many months ahead, default 6")}, planning.forecast),
        Tool("timeline", "What happened, newest first: salary changes, trips, regular payments started or stopped.", {}, planning.timeline),
        Tool("suggestions", "Things worth a look, from rules applied to your own figures.", {}, planning.suggestions),
        Tool("money_detective", "Everything odd in one list: double charges, price changes, large or unclear payments.", {}, planning.money_detective),
        Tool("net_worth", "The balance of every account in euros, month by month, from your proven statements.", {}, insight.net_worth),
        Tool("agent_list", "All the agents that read, prove and cross-check your data, and whether each one is built or planned.", {}, reports.agent_list),
        Tool(
            "verification_report",
            "What each verifier agent checked (balances, totals, second reading, payslip vs bank, invoice vs bank, continuity): counts, warnings and failures.",
            {},
            reports.verification_report,
        ),
        Tool(
            "weekly_summary",
            "The weekly summary of money: new payments and files in the last days, bills and regular payments due in the next two weeks, and what needs a check.",
            {"days": INT("How many days back, default 7")},
            reports.weekly_summary,
        ),
        Tool(
            "files_to_check",
            "Bank statements that could not be proven correct (not imported) or could not be checked, with the reason.",
            {},
            reports.files_to_check,
        ),
        Tool(
            "travel_documents",
            "Tickets and bookings found in the user's files and mail: destination, start and end dates as written in the document, and the cost. Use it for trips and travel.",
            {"place": S("Part of a destination, for example India"), "year": S("Year, for example 2026")},
            statement_import.travel_documents,
        ),
        Tool(
            "list_payslips",
            "Payslips by month: gross, tax, pension, holiday pay and net salary.",
            {"limit": N("Max months, default 36")},
            reports.list_payslips,
        ),
        Tool(
            "top_merchants",
            "Where the money went: spend per merchant, biggest first. Optional month YYYY-MM or since/until dates.",
            {"month": S("YYYY-MM"), "since": S("YYYY-MM-DD"), "until": S("YYYY-MM-DD"), "limit": N("Max rows")},
            reports.top_merchants,
        ),
        Tool(
            "income_summary",
            "Money in for a month YYYY-MM: total, by source (employer, interest, refunds, other), the month before, and the payslip figures.",
            {"month": S("YYYY-MM")},
            income_summary,
        ),
        Tool("monthly_trend", "Spent, income and net for each of the last N months.", {"months": N("How many months, default 6")}, reports.monthly_trend),
        Tool(
            "recurring_payments",
            "Subscriptions, rent, EMIs and bills: payments that repeat about monthly for a similar amount.",
            {},
            reports.recurring_payments,
        ),
        Tool("uncategorised_spending", "Merchants still in the 'other' category, biggest first.", {}, reports.uncategorised),
        Tool(
            "set_category",
            "Put all transactions from a merchant into a category (remembered for future imports).",
            {"merchant": S("Merchant name or a description containing it"), "category": S("One of: " + ", ".join(categorize.CATEGORIES))},
            reports.set_category,
            ("merchant", "category"),
        ),
        Tool("delete_transaction", "Delete a transaction by id.", {"id": N("Transaction id")}, delete_transaction, ("id",)),
    ),
)
