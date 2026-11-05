"""A printable report for one year, as a single page of HTML (print it, or save it as a PDF from the browser). Built from the same proven figures as the rest of the
app. Nothing is sent anywhere and the page loads nothing from outside."""

from __future__ import annotations

from html import escape

from . import planning, proof, wealth


def _m(x, cur: str) -> str:
    return "" if x is None else f"{cur} {x:,.2f}"


def _table(head: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "<p class=muted>Nothing for this year.</p>"
    th = "".join(f"<th>{escape(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{escape(str(c))}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"


def year_report(conn, year: str) -> str:
    cur = planning._currency(conn)
    years = {y["year"]: y for y in planning.yearly_overview(conn)["years"]}
    y = years.get(year)
    months = [r for r in planning._months(conn) if r["month"].startswith(year)]
    tax = planning.tax_summary(conn, {"year": year})
    ins = planning.insurances(conn)
    inv = planning.investments(conn)
    interest = [r for r in planning.interest(conn)["by_year"] if r["year"] == year]
    unproven = [m["month"] for m in months if not proof.month_proof(conn, {"month": m["month"]})["proven"]]
    categories = conn.execute(
        "SELECT category, SUM(amount_minor)/100.0 AS t FROM ledger WHERE kind='expense' AND category<>'transfers' AND substr(day,1,4)=? GROUP BY category ORDER BY t DESC",
        (year,),
    ).fetchall()
    nw = wealth.wealth_summary(conn)
    parts = [
        f"<h1>Orbit · {escape(year)}</h1>",
        "<p class=muted>Prepared on this computer from your own statements and documents. Facts and arithmetic only: not tax or financial advice.</p>",
        "<p class=warn>These months are not fully proven: " + ", ".join(escape(m) for m in unproven) + ". Check them before relying on this report.</p>"
        if unproven
        else "",
    ]
    if y:
        parts.append(
            "<h2>The year</h2>"
            + _table(
                ["Salary", "Money in", "Spent", "Saved", "Kept", "Interest", "Invested", "Insurance"],
                [
                    [
                        _m(y["salary"], cur),
                        _m(y["income"], cur),
                        _m(y["spent"], cur),
                        _m(y["saved"], cur),
                        "" if y["savings_rate"] is None else f"{y['savings_rate']}%",
                        _m(y["interest"], cur),
                        _m(y["invested"], cur),
                        _m(y["insurance"], cur),
                    ]
                ],
            )
            + (f"<p class=muted>Covers {y['months']} month(s) of data.</p>" if y["months"] < 12 else "")
        )
    parts.append(
        "<h2>Month by month</h2>"
        + _table(
            ["Month", "Money in", "Spent", "Saved"],
            [[m["month"], _m(m["income"], cur), _m(m["spent"], cur), _m(m["income"] - m["spent"], cur)] for m in months],
        )
    )
    parts.append("<h2>Where it went</h2>" + _table(["Category", "Spent"], [[c["category"].title(), _m(c["t"], cur)] for c in categories]))
    parts.append("<h2>Tax checklist</h2>" + _table(["Item", "Amount"], _tax_rows(tax, cur)))
    parts.append("<h2>Insurance paid</h2>" + _table(["Insurer", "Paid"], [[i["insurer"], _m(i["paid"], cur)] for i in ins["paid"] if i["year"] == year]))
    parts.append(
        "<h2>Invested</h2>"
        + _table(["Paid in"], [[_m(i["contributed"], cur)] for i in inv["contributed_by_year"] if i["year"] == year])
        + (f"<p class=muted>{escape(inv['note'])}</p>" if inv["note"] else "")
    )
    if interest:
        parts.append(
            "<h2>Interest</h2>"
            + _table(
                ["Account", "Interest", "Average balance", "Estimated rate"],
                [
                    ["…" + i["account"], _m(i["interest"], cur), _m(i["average_balance"], cur), "" if i["rate_percent"] is None else f"{i['rate_percent']}%"]
                    for i in interest
                ],
            )
        )
    if nw["net_worth"] is not None:
        parts.append(
            "<h2>What you own and owe (now)</h2>"
            + _table(
                ["Accounts (proven)", "Investments (typed)", "Assets (typed)", "Debts (typed)", "Net worth"],
                [[_m(nw["accounts"], cur), _m(nw["investments"], cur), _m(nw["assets"], cur), _m(nw["debts"], cur), _m(nw["net_worth"], cur)]],
            )
        )
    style = (
        "body{font:14px/1.5 system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#111}h1{margin:0 0 .2rem}h2{margin:1.6rem 0 .4rem;font-size:1.1rem}"
        "table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:.35rem .5rem;border-bottom:1px solid #ddd}th{color:#555;font-weight:600}"
        ".muted{color:#666}.warn{background:#fff4e5;border:1px solid #f0c36d;padding:.6rem .8rem;border-radius:8px}@media print{body{margin:0}}"
    )
    return f"<!doctype html><meta charset=utf-8><title>Orbit {escape(year)}</title><style>{style}</style>" + "".join(parts)


def _tax_rows(t: dict, cur: str) -> list[list[str]]:
    rows: list[list[str]] = []
    a = t["annual_statement"]
    if a:
        rows += [
            ["Annual statement: gross", _m(a["gross"], cur)],
            ["Annual statement: tax withheld", _m(a["tax_withheld"], cur)],
            ["Annual statement: net", _m(a["net"], cur)],
        ]
    p = t["payslips"]
    if p["count"]:
        rows += [
            [f"Payslips ({p['count']}): gross", _m(p["gross"], cur)],
            ["Payslips: tax withheld", _m(p["tax_withheld"], cur)],
            ["Payslips: pension", _m(p["pension"], cur)],
        ]
    rows += [
        ["Interest received", _m(t["interest_received"], cur)],
        ["Paid into investments", _m(t["paid_into_investments"], cur)],
        ["Insurance paid", _m(t["insurance_paid"], cur)],
    ]
    rows += [[f"Balance on 1 January, account …{b['account']}", _m(b["balance"], cur)] for b in t["balances_on_1_january"]]
    rows += [[f"Tax letter {x['date']}: {x['party'] or x['name']}", _m(x["amount"], cur)] for x in t["tax_letters"]]
    return rows
