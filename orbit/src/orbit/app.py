"""Streamlit UI: Today, Chat, Tasks, Notes, Money, People, Settings."""

from __future__ import annotations

from datetime import date

import streamlit as st

from saathi import netguard

netguard.install()

from saathi import agent, db, llm
from saathi.modules import ALL, money, notes, people, tasks, world
from saathi.modules.today import briefing_for

st.set_page_config(page_title="Saathi", page_icon="🧭", layout="wide")


@st.cache_resource
def conn():
    c = db.connect()
    db.migrate(c, ALL)
    return c


C = conn()
cur = db.get_setting(C, "currency", "INR")
page = st.sidebar.radio("Saathi", ["Today", "Chat", "Tasks", "Notes", "Money", "People", "Settings"])


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
    st.title("Ask Saathi")
    st.caption("e.g. “remind me to call Amma every Sunday”, “spent 450 on groceries”, “note: dad's BP meds are…”")
    hist = st.session_state.setdefault("history", [])
    for turn in hist:
        if turn["role"] in ("user", "assistant") and turn["content"]:
            st.chat_message(turn["role"]).write(turn["content"])
    if prompt := st.chat_input("What do you need?"):
        st.chat_message("user").write(prompt)
        try:
            with st.spinner("Thinking..."):
                reply = agent.chat(C, hist, prompt)
            st.chat_message("assistant").write(reply)
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
    q = st.text_input("Search")
    for n in notes.search_notes(C, {"query": q}):
        with st.expander(f"{n['title'] or n['body'][:50]}  ·  {n['tags']}"):
            st.write(n["body"])
            if st.button("Delete", key=f"n{n['id']}"):
                notes.delete_note(C, {"id": n["id"]})
                st.rerun()

elif page == "Money":
    st.title("Money")
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
    month = st.text_input("Month", date.today().strftime("%Y-%m"))
    s = money.summary(C, {"month": month})
    st.metric("Spent", f"{cur} {s['spent']:,.2f}")
    if s["by_category"]:
        st.bar_chart({r["category"]: r["spent"] for r in s["by_category"]})
    st.dataframe(money.list_transactions(C, {"since": f"{month}-01", "until": f"{month}-31"}), width="stretch")

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
    city = st.text_input("Home city (for weather)", db.get_setting(C, "home_city", ""))
    if st.button("Save"):
        db.set_setting(C, "currency", new.upper())
        db.set_setting(C, "model", mdl)
        db.set_setting(C, "ollama_host", oh)
        db.set_setting(C, "home_city", city)
        st.success("Saved")
    st.caption(f"Data lives in {db.home()}. The model runs locally. The only internet traffic is the public lookups below.")
    st.subheader("Everything sent to the internet")
    st.dataframe(world.network_log(C, {"limit": 100}), width="stretch")
