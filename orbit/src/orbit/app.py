"""Streamlit UI: Today, Chat, Tasks, Notes, Money, People, Settings."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import streamlit as st

from orbit import netguard

netguard.install()

from orbit import agent, applenotes, categorize, db, llm, tagging
from orbit.modules import ALL, documents, money, notes, people, tasks
from orbit.modules.today import briefing_for

st.set_page_config(page_title="Orbit", page_icon="🧭", layout="wide")


@st.cache_resource
def conn():
    c = db.connect()
    db.migrate(c, ALL)
    return c


C = conn()
cur = db.get_setting(C, "currency", "EUR")


@st.cache_resource
def _warm_model() -> bool:
    """Once per start: load the local model in the background while you look around."""
    import threading

    def work() -> None:
        try:
            client = llm.OllamaClient(db.get_setting(C, "ollama_host", "") or None)
            client.warm(client.resolve(db.get_setting(C, "model", llm.DEFAULT_MODEL)))
        except Exception:  # noqa: BLE001 - only a head start; the chat reports any real problem
            pass

    threading.Thread(target=work, daemon=True).start()
    return True


_warm_model()
page = st.sidebar.radio("Orbit", ["Today", "Chat", "Tasks", "Notes", "Documents", "Money", "People", "Settings"])


def person_names() -> dict[int, str]:
    return {p["id"]: p["name"] for p in people.list_people(C, {})}


if page == "Today":
    b = briefing_for(C, date.today())
    st.title(f"{date.today():%A, %d %B}")
    left, right = st.columns(2)
    with left:
        st.subheader("Needs attention")
        if not b["tasks_due"]:
            st.caption("Nothing due. Enjoy it.")
        for t in b["tasks_due"]:
            c1, c2 = st.columns([6, 1])
            c1.write(f"**{t['title']}**  \n:gray[{t['due']}]")
            if c2.button("Done", key=f"d{t['id']}"):
                tasks.complete_task(C, {"id": t["id"]})
                st.rerun()
        st.subheader("Coming up")
        for d in b["upcoming_dates"]:
            when = "today" if d["in_days"] == 0 else f"in {d['in_days']} days"
            age = f" (turning {d['turning']})" if d["turning"] else ""
            st.write(f"🎂 {d['name']} - {d['label']}{age}, {when}")
    with right:
        m = b["money"]
        st.subheader(f"{m['month']} money")
        a, bb, c3 = st.columns(3)
        a.metric("Spent", f"{cur} {m['spent']:,.0f}")
        bb.metric("Income", f"{cur} {m['income']:,.0f}")
        c3.metric("Net", f"{cur} {m['net']:,.0f}")
        for r in m["by_category"]:
            if "budget" in r:
                st.progress(min(r["spent"] / r["budget"], 1.0), text=f"{r['category']}: {r['spent']:,.0f} / {r['budget']:,.0f}")
            else:
                st.write(f"{r['category']}: {r['spent']:,.0f}")

elif page == "Chat":
    st.title("Ask Orbit")
    st.caption("e.g. “remind me to call Amma every Sunday”, “spent 450 on groceries”, “note: dad's BP meds are…”")
    hist = st.session_state.setdefault("history", [])
    for turn in hist:
        if turn["role"] in ("user", "assistant") and turn["content"]:
            st.chat_message(turn["role"]).write(turn["content"])
    if prompt := st.chat_input("What do you need?"):
        st.chat_message("user").write(prompt)
        try:
            trace: list = []
            with st.spinner("Thinking..."):
                reply = agent.chat(C, hist, prompt, trace=trace)
            who = trace[0]["agent"] if trace else "general"
            st.chat_message("assistant").write(reply)
            st.caption(f"{who} agent" + (f" · used {', '.join(trace[0]['tools'])}" if trace and trace[0]["tools"] else ""))
        except Exception as e:
            st.error(str(e))

elif page == "Tasks":
    st.title("Tasks & reminders")
    with st.form("add_task", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([4, 2, 2, 2])
        title = c1.text_input("Task")
        due = c2.date_input("Due", value=None)
        rec = c3.selectbox("Repeats", tasks.RECURRENCES)
        who = c4.selectbox("For", [None, *person_names()], format_func=lambda i: "-" if i is None else person_names()[i])
        if st.form_submit_button("Add") and title:
            tasks.add_task(C, {"title": title, "due": due.isoformat() if due else None, "recurrence": rec, "person_id": who})
            st.rerun()
    for t in tasks.list_tasks(C, {"status": "open"}):
        c1, c2, c3 = st.columns([6, 1, 1])
        over = t["due"] and t["due"][:10] < date.today().isoformat()
        c1.write(f"{'🔴 ' if over else ''}**{t['title']}** :gray[{t['due'] or 'no date'}"
                 f"{' · ' + t['recurrence'] if t['recurrence'] != 'none' else ''}]")
        if c2.button("Done", key=f"t{t['id']}"):
            tasks.complete_task(C, {"id": t["id"]})
            st.rerun()
        if c3.button("Delete", key=f"x{t['id']}"):
            tasks.delete_task(C, {"id": t["id"]})
            st.rerun()

elif page == "Notes":
    st.title("Notes")
    with st.form("add_note", clear_on_submit=True):
        title = st.text_input("Title")
        body = st.text_area("Note")
        tags = st.text_input("Tags (comma separated)")
        if st.form_submit_button("Save") and body:
            notes.add_note(C, {"title": title, "body": body, "tags": tags})
            st.rerun()
    inbox = Path(os.environ.get("ORBIT_INBOX", Path.home() / "OrbitInbox")) / "notes"
    if st.button("Import Apple Notes from the inbox"):
        st.success(str(applenotes.import_dir(C, inbox))) if inbox.is_dir() else st.error(f"{inbox} not found - run `orbit export-notes` on your Mac first")
    if st.button("Auto-tag untagged notes"):
        try:
            client = llm.OllamaClient(db.get_setting(C, "ollama_host", "") or None)
            n = tagging.autotag_notes(C, client, client.resolve(db.get_setting(C, "model", llm.DEFAULT_MODEL)))
        except Exception:  # model not running: rules-only still works
            n = tagging.autotag_notes(C)
        st.success(f"Tagged {n} note(s)")
    q = st.text_input("Search")
    for n in notes.search_notes(C, {"query": q}):
        with st.expander(f"{n['title'] or n['body'][:50]}  ·  {n['tags']}"):
            st.write(n["body"])
            if st.button("Delete", key=f"n{n['id']}"):
                notes.delete_note(C, {"id": n["id"]})
                st.rerun()

elif page == "Documents":
    st.title("Documents")
    st.caption("Parsed in an isolated, offline box from ~/OrbitInbox (PDF, CSV, text). Read-only here: Orbit cannot change them.")
    parsed = Path(os.environ.get("ORBIT_PARSED", Path.home() / "OrbitParsed"))
    if st.button("Load newly parsed documents"):
        st.success(str(documents.ingest_dir(C, parsed))) if parsed.is_dir() else st.error(f"{parsed} not found - start the parser")
    q = st.text_input("Search documents")
    for d in documents.search_documents(C, {"query": q, "limit": 25}):
        with st.expander(f"{d['name']}  ·  {d['kind']}  ·  {d['tags']}"):
            st.write(d["snippet"])

elif page == "Money":
    st.title("Money")
    st.caption("Everything in your finance folder (statements, payslips, invoices, receipts, tax and insurance letters, contracts) is read by the isolated, "
               "offline parser and understood by the local model. Nothing leaves this Mac.")
    parsed = Path(os.environ.get("ORBIT_PARSED", Path.home() / "OrbitParsed"))
    if st.button("Read new finance files"):
        if parsed.is_dir():
            documents.ingest_dir(C, parsed)
            bar = st.empty()
            try:
                client = llm.OllamaClient(db.get_setting(C, "ollama_host", "") or None)
                model = client.resolve(db.get_setting(C, "model", llm.DEFAULT_MODEL))
            except RuntimeError as exc:
                st.warning(f"The local model is not available ({exc}). Statements are read by the local model, so nothing was imported.")
                client = model = None
            r = money.import_statements(C, client=client, model=model, progress=bar.info)
            bar.empty()
            for problem in r["problems"]:
                st.error(problem)
            st.success(f"Read {r['files']} new file(s): {r['new_transactions']} new transactions, {r['payslips']} payslip(s); {r['already_had']} lines were already there.")
            if r["files_with_no_transactions"]:
                st.warning("No transactions could be read from: " + ", ".join(r["files_with_no_transactions"]) +
                           ". (Password-protected or scanned PDFs cannot be read yet; a CSV download from your bank works best.)")
        else:
            st.error(f"{parsed} not found - start the parser")
    with st.expander("What did Orbit make of each file?"):
        st.caption("Counts only, no content. A PDF with 0 dated lines is probably scanned or password-protected.")
        st.dataframe(money.statement_report(C), width="stretch")
    docs = money.finance_documents(C, {"limit": 200})
    if docs:
        with st.expander(f"Invoices, receipts and other files ({len(docs)})"):
            kinds = sorted({d["kind"] for d in docs})
            pick = st.selectbox("Show", ["all", *kinds])
            st.dataframe([d for d in docs if pick == "all" or d["kind"] == pick], width="stretch")
            st.caption("Totals by kind:")
            st.dataframe(money.finance_document_totals(C, {"by": "kind"}), width="stretch")
    slips = money.list_payslips(C)
    if slips:
        with st.expander(f"Payslips ({len(slips)})"):
            st.dataframe(slips, width="stretch")
    month = st.text_input("Month", date.today().strftime("%Y-%m"))
    s = money.summary(C, {"month": month})
    m1, m2, m3 = st.columns(3)
    m1.metric("Spent", f"{cur} {s['spent']:,.2f}")
    m2.metric("Income", f"{cur} {s['income']:,.2f}")
    m3.metric("Net", f"{cur} {s['net']:,.2f}")
    if s["by_category"]:
        st.subheader("By category")
        st.bar_chart({r["category"]: r["spent"] for r in s["by_category"]})
    left, right = st.columns(2)
    with left:
        st.subheader("Top merchants")
        st.dataframe(money.top_merchants(C, {"month": month}), width="stretch")
    with right:
        st.subheader("Repeating payments")
        st.dataframe(money.recurring_payments(C), width="stretch")
    trend = money.monthly_trend(C, {"months": 12})
    if trend:
        st.subheader("Month by month")
        st.bar_chart({r["month"]: r["spent"] for r in trend})
    todo = money.uncategorised(C)
    if todo:
        st.subheader("Help me sort these")
        st.caption("Choose a category once; every payment to that merchant, now and in future statements, follows it.")
        for t in todo[:10]:
            c1, c2, c3 = st.columns([3, 2, 1])
            c1.write(f"**{t['merchant']}** · {cur} {t['spent']:,.0f} · {t['times']}x")
            pick = c2.selectbox("Category", categorize.CATEGORIES, index=categorize.CATEGORIES.index("other"), key=f"cat{t['merchant']}", label_visibility="collapsed")
            if c3.button("Save", key=f"save{t['merchant']}") and pick != "other":
                money.set_category(C, {"merchant": t["merchant"], "category": pick})
                st.rerun()
    with st.expander("Add one by hand"):
        with st.form("add_tx", clear_on_submit=True):
            c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 3, 2])
            amt = c1.number_input(f"Amount ({cur})", min_value=0.0, step=10.0)
            kind = c2.selectbox("Type", ["expense", "income"])
            cat = c3.text_input("Category", "other")
            note = c4.text_input("Note")
            day = c5.date_input("Date", date.today())
            if st.form_submit_button("Add") and amt > 0:
                money.add_transaction(C, {"amount": amt, "kind": kind, "category": cat, "note": note, "date": day.isoformat()})
                st.rerun()
    st.dataframe(money.list_transactions(C, {"since": f"{month}-01", "until": f"{month}-31", "limit": 500}), width="stretch")

elif page == "People":
    st.title("Family & people")
    with st.form("add_person", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3, 2, 2, 3])
        name = c1.text_input("Name")
        rel = c2.text_input("Relation")
        bday = c3.date_input("Birthday", value=None, min_value=date(1900, 1, 1))
        about = c4.text_input("About (health notes, likes...)")
        if st.form_submit_button("Add") and name:
            pid = people.add_person(C, {"name": name, "relation": rel, "about": about})["id"]
            if bday:
                people.add_important_date(C, {"person_id": pid, "label": "Birthday", "date": bday.isoformat()})
            st.rerun()
    for p in people.list_people(C, {}):
        st.write(f"**{p['name']}** :gray[{p['relation']}] {p['about']}")

else:
    st.title("Settings")
    new = st.text_input("Currency code", cur)
    mdl = st.text_input("Local model (Ollama)", db.get_setting(C, "model", llm.DEFAULT_MODEL))
    oh = st.text_input("Ollama address", db.get_setting(C, "ollama_host", "") or llm.host())
    if st.button("Save"):
        db.set_setting(C, "currency", new.upper())
        db.set_setting(C, "model", mdl)
        db.set_setting(C, "ollama_host", oh)
        st.success("Saved")
    st.caption(f"Data lives in {db.home()}. The model runs locally. Orbit makes no internet requests.")
