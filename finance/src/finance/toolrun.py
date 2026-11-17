"""Running one tool for the one assistant: the arguments are coerced to the declared types (small models send numbers as strings), a failure comes back
as data the model can read, and the tools no AI may run are named here."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from kit import money as kit_money

from .modules import ALL
from .modules import tools as registry

NEVER_BY_AI = frozenset({"delete_transaction"})  # your imported payments are the record: no assistant may delete one, whatever it is told

# What each tool does to the person's data. Every tool is named in exactly one set (a test fails for a tool that is in none), so a new tool must be classified when it is added.
CONSEQUENTIAL = frozenset(  # changes the money records: the assistant only PREPARES these; they happen when the person says yes in a later message
    {
        "add_transaction",
        "set_budget",
        "set_category",
        "assign_to_event",
        "remove_from_event",
        "update_event",
        "add_holding",
        "update_holding",
        "add_goal",
    }
)
DELETES = frozenset(  # run only if the person's own words ask for a delete (and never delete_transaction)
    {"delete_event", "delete_goal", "delete_holding", "delete_note", "delete_person", "delete_task", "delete_transaction"}
)
ROUTINE_WRITES = frozenset(  # the person's organiser, and reading their own files: run at once, but every one of them is also open to the person to undo
    {
        "add_person",
        "update_person",
        "add_important_date",
        "add_task",
        "complete_task",
        "reschedule_task",
        "add_note",
        "update_note",
        "create_event",
        "import_statements",
    }
)

READ_ONLY = frozenset(  # change nothing (a test runs each one and checks that the database is unchanged)
    {
        "accounts_overview",
        "agent_list",
        "bills_due",
        "budget_progress",
        "check_totals",
        "currencies",
        "current_time",
        "daily_briefing",
        "daily_spending",
        "explore_payments",
        "family_money",
        "files_to_check",
        "finance_document_totals",
        "finance_documents",
        "forecast",
        "income_breakdown",
        "income_summary",
        "insurances",
        "interest_earned",
        "investments",
        "investments_overview",
        "list_events",
        "list_goals",
        "list_holdings",
        "list_payslips",
        "list_people",
        "list_tasks",
        "list_transactions",
        "merchant_history",
        "money_detective",
        "month_breakdown",
        "month_proof",
        "monthly_trend",
        "net_worth",
        "payment_detail",
        "recurring_payments",
        "savings_overview",
        "search_everything",
        "search_notes",
        "spending_between",
        "spending_by_main",
        "spending_summary",
        "suggestions",
        "tax_summary",
        "timeline",
        "top_merchants",
        "travel_documents",
        "uncategorised_spending",
        "upcoming_dates",
        "upcoming_payments",
        "verification_report",
        "wealth_summary",
        "weekly_summary",
        "yearly_overview",
    }
)


def _coerce(tool, args: dict[str, Any]) -> dict[str, Any]:
    """Small local models often send numbers as strings; fix by the declared type."""
    out = dict(args)
    for k, v in args.items():
        t = tool.properties.get(k, {}).get("type")
        try:
            if t == "integer" and isinstance(v, (str, float)):
                out[k] = int(float(v))
            elif t == "number" and isinstance(v, str):
                out[k] = float(kit_money.parse_amount(v))
        except ValueError:
            pass
    return out


def run_tool(conn: sqlite3.Connection, name: str, args: dict[str, Any] | str, allowed: frozenset[str] | None = None) -> tuple[str, bool]:
    tool = registry(ALL).get(name)
    if tool is None or (allowed is not None and name not in allowed):
        return json.dumps({"error": f"tool {name!r} is not available"}), True
    try:
        parsed: dict[str, Any] = json.loads(args or "{}") if isinstance(args, str) else args
        return json.dumps(tool.fn(conn, _coerce(tool, parsed)), default=str), False
    except Exception as e:  # noqa: BLE001 - any tool failure is reported to the model so it can correct itself
        conn.rollback()
        return json.dumps({"error": f"{type(e).__name__}: {e}"}), True
