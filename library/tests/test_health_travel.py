"""Health (locked; values and medicines exactly as printed) and Travel (trips from tickets, bookings and photos)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from kit import db

from library import store, tools, travel, web


@pytest.fixture
def lib(tmp_path):
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    n = [0]

    def add(name, kind, text="t", **facts):
        n[0] += 1
        conn.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, facts, judged, ready) VALUES (?,?,?,?,?,?,1,?)",
            (f"{n[0]:064x}", name, "pdf", text, "", json.dumps({"kind": kind, **facts}), n[0]),
        )
        conn.commit()

    store.set_health_unlocked(False)
    yield SimpleNamespace(conn=conn, add=add, state=SimpleNamespace(engine=lambda: None, picture_text=lambda: None))
    store.set_health_unlocked(False)


def _blood(lib):
    health = {
        "values": [{"test": "Hemoglobine", "value": "8,4", "number": 8.4, "unit": "mmol/L", "range": "7,5 - 10,0"}],
        "medicines": [{"name": "Metformine", "dose": "500 mg", "duration": ""}],
        "follow_up": "2099-06-01",
    }
    lib.add("bloed-maart.pdf", "medical", title="Blood test", date="2026-03-01", party="Kliniek", health=health)
    health2 = {"values": [{"test": "hemoglobine", "value": "9,0", "number": 9.0, "unit": "mmol/L", "range": "7,5 - 10,0"}], "medicines": [], "follow_up": None}
    lib.add("bloed-juni.pdf", "medical", title="Blood test", date="2026-06-02", party="Kliniek", health=health2)


def test_health_is_locked_nothing_comes_out_and_the_assistant_is_told_why(lib):
    _blood(lib)
    for fn in (store.health_timeline, store.health_values, store.health_medicines):
        assert fn(lib.conn) == {"locked": True, "held_back": 2}
    out = tools.run(lib.state, lib.conn, "health_values", {})
    assert out["ok"] and out["data"]["locked"] is True and "unlock" in out["data"]["note"].lower()


def test_unlocked_health_shows_each_measurement_over_time_exactly_as_printed(lib):
    _blood(lib)
    store.set_health_unlocked(True)
    tests = store.health_values(lib.conn)["tests"]
    assert len(tests) == 1 and tests[0]["test"] == "Hemoglobin" and tests[0]["unit"] == "mmol/L"
    assert [(r["date"], r["value"], r["range"]) for r in tests[0]["readings"]] == [("2026-03-01", "8,4", "7,5 - 10,0"), ("2026-06-02", "9,0", "7,5 - 10,0")]
    assert store.health_values(lib.conn, "cholesterol")["tests"] == []
    assert [m["name"] for m in store.health_medicines(lib.conn)["medicines"]] == ["Metformine"]
    assert [d["name"] for d in store.health_timeline(lib.conn)["documents"]] == ["bloed-juni.pdf", "bloed-maart.pdf"]  # newest first
    assert [f["date"] for f in store.health_followups(lib.conn, "2026-07-01")["follow_ups"]] == ["2099-06-01"]
    assert store.health_followups(lib.conn, "2100-01-01")["follow_ups"] == []


def test_medical_details_are_filled_for_documents_judged_before_and_use_the_model_once(lib):
    lib.add("oud.pdf", "medical", text="Hemoglobine 8,4 mmol/L", title="Old", date="2025-01-01")
    calls = []

    class Model:
        def chat(self, model, messages, schema=None, **kw):
            calls.append(1)
            return {"content": json.dumps({"values": [{"test": "Hemoglobine", "value": "8,4", "unit": "mmol/L"}]})}

    assert store.fill_health_details(lib.conn, Model(), "m") == 1 and store.fill_health_details(lib.conn, Model(), "m") == 0 and len(calls) == 1
    store.set_health_unlocked(True)
    assert store.health_values(lib.conn)["tests"][0]["readings"][0]["value"] == "8,4"


def test_trips_come_from_tickets_and_bookings_with_exact_booked_totals(lib):
    lib.add(
        "flight.pdf", "ticket", title="KLM", start_date="2099-01-10", end_date="2099-01-10", place="Bengaluru", reference="ABC123", total=612.5, currency="EUR"
    )
    lib.add("hotel.pdf", "booking", title="Taj", start_date="2099-01-10", end_date="2099-01-20", place="Bengaluru", total=300.25, currency="EUR")
    lib.add("old.pdf", "ticket", title="Old", start_date="2020-05-01", end_date="2020-05-05", place="Lisbon")
    lib.add("receipt.pdf", "receipt", title="Dinner", date="2099-01-12", total=45.0, currency="EUR")
    found = travel.trips(lib.conn, None, "2026-11-10")
    assert [(t["place"], t["status"]) for t in found] == [("Bengaluru", "upcoming"), ("Lisbon", "past")]  # not yet over first, then the past, newest first
    d = travel.detail(lib.conn, None, "Bengaluru", "2099-01-10", "2099-01-20")
    assert [t["name"] for t in d["tickets"]] == ["flight.pdf", "hotel.pdf"] and d["booked_totals"] == {"EUR": 912.75}
    assert [o["name"] for o in d["other_documents"]] == ["receipt.pdf"] and d["tickets"][0]["reference"] == "ABC123"
    out = tools.run(lib.state, lib.conn, "trip_details", {"place": "bengaluru"})
    assert out["ok"] and out["data"]["trips"][0]["booked_totals"] == {"EUR": 912.75}
    assert [t["place"] for t in tools.run(lib.state, lib.conn, "upcoming_trips", {})["data"]["trips"]] == ["Bengaluru"]


def test_the_calendar_file_lists_every_trip_as_whole_days():
    ics = travel.calendar([{"place": "Goa, India", "start": "2026-12-30", "end": "2027-01-02"}])
    assert (
        "DTSTART;VALUE=DATE:20261230" in ics and "DTEND;VALUE=DATE:20270103" in ics and "SUMMARY:Trip: Goa India" in ics and ics.startswith("BEGIN:VCALENDAR")
    )


def test_the_travel_and_health_routes_exist_and_a_trip_needs_real_days(lib):
    for route in ("/api/travel/trips", "/api/travel/trip", "/api/medical/timeline", "/api/medical/values", "/api/medical/medicines", "/api/medical/followups"):
        assert route in web.GET_ROUTES
    with pytest.raises(web.Fail):
        web._get_travel_trip(lib.state, lib.conn, {"place": "x", "start": "not", "end": "2026-01-01"})


def _packing(lib, action, **extra):
    return travel.packing_action(lib.conn, {"place": "Goa", "start": "2099-01-10", "end": "2099-01-14", "action": action, **extra})


def test_a_packing_list_starts_from_a_standard_list_whose_quantities_follow_from_the_days(lib):
    r = _packing(lib, "seed")  # five days
    texts = [i["text"] for i in r["items"]]
    assert "Tops: 5" in texts and "Underwear and socks: 6" in texts and "Trousers or skirts: 3" in texts and "Passport or ID" in texts
    assert r["packed"] == 0 and r["total"] == len(r["items"]) and r["items"][0]["section"] == "Documents"
    assert [
        i["text"]
        for i in travel.packing_action(lib.conn, {"place": "X", "start": "2099-01-01", "end": "2099-03-01", "action": "seed"})["items"]
        if i["text"].startswith(("Tops", "Underwear", "Trousers"))
    ] == [
        "Tops: 7",
        "Underwear and socks: 8",
        "Trousers or skirts: 4",
    ]  # a long trip: you wash, so the numbers stop growing
    with pytest.raises(ValueError, match="already has a list"):
        _packing(lib, "seed")


def test_items_can_be_added_ticked_and_removed_and_each_trip_has_its_own_list(lib):
    _packing(lib, "seed")
    added = _packing(lib, "add", text="  Camera   and lens ", section="Electronics")
    item = next(i for i in added["items"] if i["text"] == "Camera and lens")
    assert item["section"] == "Electronics" and item["done"] == 0
    assert _packing(lib, "toggle", id=item["id"])["packed"] == 1 and _packing(lib, "toggle", id=item["id"])["packed"] == 0
    assert all(i["id"] != item["id"] for i in _packing(lib, "delete", id=item["id"])["items"])
    assert travel.packing(lib.conn, "Lisbon", "2099-01-10")["total"] == 0  # another trip: nothing
    other = travel.packing_action(lib.conn, {"place": "Lisbon", "start": "2099-01-10", "end": "2099-01-12", "action": "add", "text": "Guidebook"})
    assert _packing(lib, "toggle", id=other["items"][0]["id"])["packed"] == 0  # an item of another trip cannot be changed from this one
    for bad in ({"action": "add", "text": "  "}, {"action": "nonsense"}):
        with pytest.raises(ValueError):
            _packing(lib, bad["action"], **{k: v for k, v in bad.items() if k != "action"})


def test_the_assistant_can_say_what_is_left_to_pack(lib):
    lib.add("flight.pdf", "ticket", title="KLM", start_date="2099-01-10", end_date="2099-01-14", place="Goa")
    _packing(lib, "seed")
    first = travel.packing(lib.conn, "Goa", "2099-01-10")["items"][0]
    _packing(lib, "toggle", id=first["id"])
    out = tools.run(lib.state, lib.conn, "packing_list", {"place": "goa"})["data"]["lists"][0]
    assert out["packed"] == 1 and first["text"] not in out["still_to_pack"] and len(out["still_to_pack"]) == out["total"] - 1


def test_the_packing_routes_exist_and_refuse_a_trip_without_days(lib):
    assert "/api/travel/packing" in web.GET_ROUTES and "/api/travel/packing" in web.POST_ROUTES
    with pytest.raises(web.Fail):
        web._post_packing(lib.state, lib.conn, {"place": "Goa", "start": "x", "end": "y", "action": "seed"})


def test_a_result_is_flagged_only_against_the_range_the_report_itself_prints():
    flag = store.range_flag
    assert [flag(8.4, "7,5 - 10,0"), flag(7.4, "7,5 - 10,0"), flag(10.1, "7.5-10.0"), flag(7.5, "7,5 - 10,0"), flag(10.0, "7,5 - 10,0")] == [
        "in_range",
        "below_range",
        "above_range",
        "in_range",
        "in_range",
    ]
    assert [flag(4.9, "< 5,0"), flag(5.0, "< 5,0"), flag(5.0, "<= 5,0"), flag(3.1, "> 3"), flag(3.0, "> 3"), flag(3.0, ">= 3")] == [
        "in_range",
        "above_range",
        "in_range",
        "in_range",
        "below_range",
        "in_range",
    ]
    assert (
        flag(None, "7,5 - 10,0") == "no_range" and flag(8.0, "") == "no_range" and flag(8.0, "normal") == "no_range"
    )  # no number, no range, or a range that cannot be read


def test_lab_values_are_grouped_by_common_test_with_the_latest_flag_and_the_change_since_the_reading_before(lib):
    def rec(name, date, *values):
        lib.add(
            name,
            "medical",
            title="Lab",
            date=date,
            party="Kliniek",
            health={"values": [dict(zip(("test", "value", "number", "unit", "range"), v, strict=True)) for v in values], "medicines": [], "follow_up": None},
        )

    rec(
        "a.pdf",
        "2026-01-10",
        ("Cholesterol totaal", "5,0", 5.0, "mmol/L", "< 5,0"),
        ("Hemoglobine", "8,4", 8.4, "mmol/L", "7,5 - 10,0"),
        ("Zink", "12", 12.0, "umol/L", ""),
    )
    rec(
        "b.pdf",
        "2026-06-10",
        ("Total cholesterol", "5,6", 5.6, "mmol/L", "< 5,0"),
        ("Hb", "9,0", 9.0, "mmol/L", "7,5 - 10,0"),
        ("Zink", "11", 11.0, "umol/L", ""),
    )
    store.set_health_unlocked(True)
    r = store.health_values(lib.conn)
    chol = next(g for g in r["common"] if g["test"] == "Cholesterol (total)")
    assert [x["value"] for x in chol["readings"]] == ["5,0", "5,6"] and chol["flag"] == "above_range"  # two spellings, one test
    assert chol["change"] == {"since": "2026-01-10", "absolute": 0.6, "percent": 12.0, "direction": "up"}
    hb = next(g for g in r["common"] if g["test"] == "Hemoglobin")
    assert hb["flag"] == "in_range" and [g["test"] for g in r["attention"]] == ["Cholesterol (total)"] and [g["test"] for g in r["other"]] == ["Zink"]
    assert [g["test"] for g in r["common"]] == ["Hemoglobin", "Cholesterol (total)"]  # common tests in a fixed, familiar order
    assert next(g for g in r["other"])["flag"] == "no_range" and "not a diagnosis" in r["note"]
    out = tools.run(lib.state, lib.conn, "health_values", {"test": "cholesterol"})
    assert out["ok"] and [g["test"] for g in out["data"]["tests"]] == ["Cholesterol (total)"]  # narrowed to the test asked about
    assert [g["test"] for g in out["data"]["outside_printed_range"]] == ["Cholesterol (total)"] and out["data"]["outside_printed_range"][0]["latest"][
        "flag"
    ] == "above_range"
    assert "never what it means for health" in out["data"]["note"]


def test_a_document_in_the_health_folder_is_a_health_document_whatever_the_model_said(lib):
    lib.conn.execute(
        "INSERT INTO documents (sha256, name, kind, text, area, facts, judged, ready) VALUES (?,?,?,?,?,?,1,50)",
        ("e" * 64, "scan.pdf", "pdf", "haemoglobine 8,4", "health", json.dumps({"kind": "other", "title": "Scan", "date": "2026-02-02"})),
    )
    lib.conn.execute(
        "INSERT INTO documents (sha256, name, kind, text, area, facts, judged) VALUES (?,?,?,?,?,?,0)",
        ("f" * 64, "new.pdf", "pdf", "unread secret", "health", ""),
    )
    lib.conn.commit()
    assert store.list_documents(lib.conn, ["other"]) == [] and store.get_document(lib.conn, "e" * 64) is None
    assert not any(
        "unread secret" in p["text"] or "haemoglobine" in p["text"] for p in store.passages(lib.conn, "haemoglobine secret")
    )  # not searchable while locked, judged or not
    assert store.hidden_health_count(lib.conn) == 2 and {"kind": "other", "count": 1} not in store.by_kind(lib.conn)
    store.set_health_unlocked(True)
    assert [d["name"] for d in store.health_timeline(lib.conn)["documents"]] == ["scan.pdf"] and store.get_document(lib.conn, "e" * 64)


def test_the_folders_script_gives_the_reader_category_folders_and_listed_ones_read_only_and_skips_bad_lines(tmp_path):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    icloud = tmp_path / "iCloud Drive" / "Health"
    icloud.mkdir(parents=True)
    (tmp_path / "plain").mkdir()
    (tmp_path / "pl:ain").mkdir()  # a folder whose name has a colon: compose cannot mount it, so it is refused
    lst = tmp_path / "folders.txt"
    lst.write_text(
        f"# a comment\nhealth={icloud}\ntravel={tmp_path / 'plain'}\nmail={tmp_path / 'plain'}\nBAD NAME={tmp_path / 'plain'}\nhealth={tmp_path / 'missing'}\nhealth={tmp_path / 'pl:ain'}\n"
    )
    out = tmp_path / "out.yml"
    done = subprocess.run(
        ["bash", str(root / "scripts" / "folders-compose.sh"), str(out)],
        env={"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(lst), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    text = out.read_text()
    assert (
        'LIBRARY_COLLECTIONS: "finance=/collections/finance,health=/collections/health-1,travel=/collections/travel-2"' in text
    )  # the person has a folder for each: no empty default beside it
    assert "AtlasHealth" not in text and "AtlasTravel" not in text
    assert f'"{icloud}:/collections/health-1:ro"' in text and all(line.endswith(':ro"') for line in text.splitlines() if line.startswith("      - "))
    assert "not 'mail'" in done.stderr and "no such folder" in done.stderr and "colon" in done.stderr  # bad lines are named, not silently dropped
    assert (
        not (tmp_path / "AtlasHealth").exists() and not (tmp_path / "AtlasTravel").exists()
    )  # no empty folders are made in the home folder when the person has their own


def test_add_folder_writes_the_choice_to_the_list_only_and_refuses_bad_ones(tmp_path):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    folder = tmp_path / "iCloud Drive" / "Health"
    folder.mkdir(parents=True)
    (folder / "report.pdf").write_text("x")
    (folder / ".old.pdf.icloud").write_text("")  # a file that is only in the cloud
    lst = tmp_path / "list.txt"
    env = {"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(lst), "ATLAS_SKIP_APPLY": "1", "PATH": "/usr/bin:/bin"}

    def add(*args):
        return subprocess.run(["bash", str(root / "scripts" / "add-folder.sh"), *args], env=env, capture_output=True, text=True, check=False)

    first = add("health", str(folder))
    assert first.returncode == 0 and f"health={folder}" in lst.read_text().splitlines()
    assert "Found 1 files" in first.stdout and "1 more are only in iCloud" in first.stdout and "Download Now" in first.stdout
    assert "Already added" in add("health", str(folder)).stdout and lst.read_text().count(f"health={folder}") == 1
    for bad in (("mail", str(folder)), ("Health", str(folder)), ("health", str(tmp_path / "nope"))):
        r = add(*bad)
        assert r.returncode == 1 and "Not added" in r.stderr
    assert [line for line in lst.read_text().splitlines() if line and not line.startswith("#")] == [f"health={folder}"]  # nothing bad was written


def test_folders_named_after_the_categories_in_icloud_drive_are_found_without_adding_anything(tmp_path):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    for name in ("Health", "Finance", "Personal", "Holiday photos"):
        (icloud / name).mkdir(parents=True)
    (icloud / "Atlas" / "Travel").mkdir(parents=True)
    (icloud / "Atlas" / "Others").mkdir(parents=True)
    (icloud / "Recipes").mkdir()
    out = tmp_path / "out.yml"
    done = subprocess.run(
        ["bash", str(root / "scripts" / "folders-compose.sh"), str(out)],
        env={"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(tmp_path / "none.txt"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    text = out.read_text()
    for name in ("Health", "Finance", "Personal"):
        assert f'"{icloud / name}:' in text
    assert f'"{icloud / "Atlas" / "Travel"}:' in text and f'"{icloud / "Atlas" / "Others"}:' in text
    assert "Recipes" not in text and "Holiday photos" not in text and all(line.endswith(':ro"') for line in text.splitlines() if line.startswith("      - "))
    assert "as health" in done.stderr and "as others" in done.stderr
    names = next(line for line in text.splitlines() if "LIBRARY_COLLECTIONS" in line)
    assert "health=/collections/health-" in names and "personal=/collections/personal-" in names and "others=/collections/others-" in names


def test_category_folders_are_also_found_inside_documents_and_on_the_desktop_each_taken_once(tmp_path):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    (icloud / "Documents" / "Health").mkdir(parents=True)
    (tmp_path / "Documents" / "Finance").mkdir(parents=True)
    (tmp_path / "Desktop" / "Travel").mkdir(parents=True)
    (tmp_path / "Desktop" / "Random").mkdir()
    (tmp_path / "Documents" / "Others").mkdir()
    (tmp_path / "Documents" / "Personal").symlink_to(icloud / "Documents" / "Health")  # the same folder reached a second way
    out = tmp_path / "out.yml"
    done = subprocess.run(
        ["bash", str(root / "scripts" / "folders-compose.sh"), str(out)],
        env={"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(tmp_path / "none.txt"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    text = out.read_text()
    assert (
        f'"{icloud / "Documents" / "Health"}:' in text and f'"{tmp_path / "Documents" / "Finance"}:' in text and f'"{tmp_path / "Desktop" / "Travel"}:' in text
    )
    assert f'"{tmp_path / "Documents" / "Others"}:' in text and "Random" not in text
    assert done.stderr.count("as health") == 1 and "as personal" not in done.stderr  # reached twice, read once


def test_the_same_folder_is_read_once_however_it_is_reached(tmp_path):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    (icloud / "Health").mkdir(parents=True)
    (tmp_path / "linked").symlink_to(icloud / "Health")
    lst = tmp_path / "list.txt"
    lst.write_text(
        f"health={icloud / 'Health'}\nhealth={tmp_path / 'linked'}\nhealth={icloud / 'Health'}/\ntravel={tmp_path / 'AtlasHealth'}\n"
    )  # four lines, one folder (and one more that is a default)
    out = tmp_path / "out.yml"
    done = subprocess.run(
        ["bash", str(root / "scripts" / "folders-compose.sh"), str(out)],
        env={"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(lst), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    text = out.read_text()
    assert text.count(str(icloud / "Health")) == 1 and done.stderr.count("is already read") >= 2  # the folder is mounted once; the repeats are named
    assert text.count("/collections/health-") == 2  # one in the variable, one mount
    assert (
        ":/collections/travel:ro" in text and ":/collections/health:ro" not in text
    )  # no travel folder of theirs: the default is made; health they have: no default
    folder = tmp_path / "Real"
    folder.mkdir()
    (tmp_path / "alias").symlink_to(folder)
    env = {"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(tmp_path / "l2.txt"), "ATLAS_SKIP_APPLY": "1", "PATH": "/usr/bin:/bin"}
    for path in (folder, tmp_path / "alias", f"{folder}/"):
        subprocess.run(["bash", str(root / "scripts" / "add-folder.sh"), "personal", str(path)], env=env, capture_output=True, text=True, check=False)
    assert len([ln for ln in (tmp_path / "l2.txt").read_text().splitlines() if ln and not ln.startswith("#")]) == 1  # added once, not three times


def test_a_folder_called_other_counts_as_others(tmp_path):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    (icloud / "Other").mkdir(parents=True)
    out = tmp_path / "out.yml"
    subprocess.run(
        ["bash", str(root / "scripts" / "folders-compose.sh"), str(out)],
        env={"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(tmp_path / "none.txt"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    assert "others=/collections/others-1" in out.read_text()


def test_the_empty_default_folders_are_made_only_when_there_is_no_folder_of_that_kind_or_files_in_them(tmp_path):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "out.yml"
    env = {"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(tmp_path / "none.txt"), "PATH": "/usr/bin:/bin"}

    def run():
        subprocess.run(["bash", str(root / "scripts" / "folders-compose.sh"), str(out)], env=env, capture_output=True, text=True, check=True)
        return out.read_text()

    text = run()  # nothing of the person's own: the default folders are made and read, so there is a place to drop files
    assert (tmp_path / "AtlasHealth").is_dir() and ":/collections/health:ro" in text and ":/collections/travel:ro" in text
    (tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs" / "Health").mkdir(parents=True)
    text = run()
    assert ":/collections/health:ro" not in text and "/collections/health-1" in text  # their own folder found: the empty default is not listed beside it
    (tmp_path / "AtlasHealth" / "note.txt").write_text("x")
    text = run()
    assert ":/collections/health:ro" in text and "/collections/health-1" in text  # files dropped in the default folder are still read


def _found(tmp_path, *folders):
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    icloud = tmp_path / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    for folder in folders:
        (icloud / folder).mkdir(parents=True)
    out = tmp_path / "out.yml"
    done = subprocess.run(
        ["bash", str(root / "scripts" / "folders-compose.sh"), str(out)],
        env={"HOME": str(tmp_path), "ATLAS_FOLDERS_FILE": str(tmp_path / "none.txt"), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=True,
    )
    return icloud, out.read_text(), done.stderr


def test_category_folders_are_found_three_levels_deep_and_by_their_dutch_names(tmp_path):
    icloud, text, said = _found(tmp_path, "Docs/Archive/Others", "Papieren/Gezondheid", "Overig", "Reizen", "Persoonlijk", "Financiën", "Deep/One/Two/Health")
    for folder, label in (
        ("Docs/Archive/Others", "others"),
        ("Papieren/Gezondheid", "health"),
        ("Reizen", "travel"),
        ("Persoonlijk", "personal"),
        ("Financiën", "finance"),
    ):
        assert f"{icloud / folder} as {label}" in said, folder
    assert f"{icloud / 'Overig'} as others" in said  # a second others folder is a second folder, read as well
    assert "Deep/One/Two/Health" not in text  # four levels down: not looked for


def test_a_folder_inside_one_already_read_is_not_read_twice(tmp_path):
    icloud, text, said = _found(tmp_path, "Personal/Health", "Personal/Travel", "Finance/Others")
    assert said.count("Atlas will read") == 2 and f"{icloud / 'Personal'} as personal" in said and f"{icloud / 'Finance'} as finance" in said
    assert "Personal/Health" not in text and "Finance/Others" not in text  # the parent already covers them: the same files are not read under two kinds
