"""Every write to the person's files goes through one gate: prepared and only described, shown in a confirmation window, confirmed by the person pressing the
button (no tool can), checked again at that moment, done with a journal, verified, audited and undoable."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from images.config import ENV_INTERNAL
from kit import db
from PIL import Image

from library import changes, filing, indexer, pictures, store, tools, web
from tests.test_pictures import engine_with_fake_models


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_INTERNAL, "1")
    monkeypatch.setenv("LIBRARY_PICTURES_DRIVE", str(tmp_path / "drive"))
    monkeypatch.setenv("LIBRARY_PHOTOS", str(tmp_path / "drive" / "Photos"))
    monkeypatch.setattr(changes, "MIN_OPEN_SECONDS", 0.0)
    photos = tmp_path / "drive" / "Photos"
    photos.mkdir(parents=True)
    Image.new("RGB", (120, 100), (220, 20, 20)).save(photos / "receipt.jpg")  # the fake reader finds text in red pictures
    Image.new("RGB", (120, 100), (20, 20, 220)).save(photos / "beach.jpg")
    engine = engine_with_fake_models()
    indexer.run_once(engine)
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    state = SimpleNamespace(engine=lambda: engine, picture_text=lambda: None)
    return SimpleNamespace(engine=engine, conn=conn, state=state, photos=photos)


def names(folder):
    return sorted(p.name for p in folder.rglob("*") if p.is_file())


def prepare(w, kind="move", **args):
    tool = {"move": "preview_move_pictures", "delete": "preview_delete_pictures", "export": "preview_export_pictures"}[kind]
    out = tools.run(w.state, w.conn, tool, {"query": "kassabon", "folder": "Receipts", **args})
    assert out["ok"], out
    return out


def open_window(w, change_id):
    return changes.details(w.conn, w.state, change_id)


def audited(w, change_id):
    return [r["action"] for r in w.conn.execute("SELECT action FROM write_audit WHERE change_id=? ORDER BY id", (change_id,))]


def test_the_assistant_can_only_prepare_never_confirm(world):
    offered = {t.name for t in tools.TOOLS}
    assert {"preview_move_pictures", "preview_delete_pictures", "preview_export_pictures", "list_changes"} <= offered
    assert not {n for n in offered if n.startswith(("apply", "confirm", "undo"))}  # there is no tool that carries a change out or takes it back
    out = prepare(world)
    assert "NOT DONE" in out["data"]["status"] and out["data"]["files"] == 1 and "nonce" not in str(out["data"])  # the model never sees what opens the window
    assert out["items"][0]["kind"] == "confirm" and out["items"][0]["link"] == f"#/changes?id={out['data']['change_id']}"
    assert names(world.photos) == ["beach.jpg", "receipt.jpg"]  # nothing has moved


def test_a_move_is_done_only_after_the_window_was_opened_and_the_right_key_is_pressed(world):
    change = prepare(world)["data"]["change_id"]
    assert changes.confirm(world.state, world.conn, change, "anything")["error"].startswith("this is not the window")  # never opened, no key
    window = open_window(world, change)
    assert window["files"] == 1 and window["problems"] == [] and window["list"][0]["name"] == "receipt.jpg" and window["nonce"]
    assert "not the window" in changes.confirm(world.state, world.conn, change, "wrong")["error"]
    done = changes.confirm(world.state, world.conn, change, window["nonce"])
    assert done["ok"] and done["status"] == "done" and done["batch"] and "moved 1 of 1" in done["text"]
    assert (world.photos / "Receipts" / "receipt.jpg").is_file() and not (world.photos / "receipt.jpg").exists() and (world.photos / "beach.jpg").is_file()
    assert (
        world.engine.db.connect().execute("SELECT rel_path FROM items WHERE rel_path LIKE '%receipt%'").fetchone()[0] == "Receipts/receipt.jpg"
    )  # the index followed the file
    assert "already done" in changes.confirm(world.state, world.conn, change, window["nonce"])["error"]
    assert audited(world, change) == ["prepared", "refused", "opened", "refused", "confirmed", "refused"]


def test_the_window_must_have_been_open_for_a_moment_before_it_can_be_confirmed(world, monkeypatch):
    monkeypatch.setattr(changes, "MIN_OPEN_SECONDS", 60.0)
    change = prepare(world)["data"]["change_id"]
    nonce = open_window(world, change)["nonce"]
    assert "looked at" in changes.confirm(world.state, world.conn, change, nonce)["error"]
    assert (world.photos / "receipt.jpg").exists()


@pytest.mark.parametrize("spoil, wording", [("change", "changed since this was prepared"), ("remove", "no longer where it was"), ("clash", "already exists")])
def test_a_change_is_checked_again_when_confirmed_and_refused_if_anything_is_different(world, spoil, wording):
    change = prepare(world)["data"]["change_id"]
    nonce = open_window(world, change)["nonce"]
    receipt = world.photos / "receipt.jpg"
    if spoil == "change":
        Image.new("RGB", (60, 50), (255, 0, 0)).save(receipt)
    elif spoil == "remove":
        receipt.unlink()
    else:
        (world.photos / "Receipts").mkdir()
        (world.photos / "Receipts" / "receipt.jpg").write_bytes(b"something else already here")
    refused = changes.confirm(world.state, world.conn, change, nonce)
    assert refused["ok"] is False and wording in refused["error"]
    assert not (spoil == "change" and not receipt.exists())  # nothing was touched


def test_nothing_is_changed_while_the_pictures_are_being_read(world):
    change = prepare(world)["data"]["change_id"]
    window = open_window(world, change)
    pictures.write_state(world.engine, True, "Reading pictures…")
    assert any("being read" in p for p in changes.details(world.conn, world.state, change)["problems"])
    assert "being read" in changes.confirm(world.state, world.conn, change, window["nonce"])["error"]
    assert (world.photos / "receipt.jpg").exists()
    pictures.write_state(world.engine, False)
    assert changes.confirm(world.state, world.conn, change, window["nonce"])["ok"]


def test_one_change_cannot_touch_more_files_than_the_limit(world, monkeypatch):
    monkeypatch.setattr(changes, "MAX_FILES", 0)
    change = prepare(world)["data"]["change_id"]
    window = open_window(world, change)
    assert any("most one change may touch" in p for p in window["problems"])
    assert "most one change may touch" in changes.confirm(world.state, world.conn, change, window["nonce"])["error"]


def test_a_forgotten_change_expires_and_a_cancelled_one_cannot_be_confirmed(world):
    old = prepare(world)["data"]["change_id"]
    nonce = open_window(world, old)["nonce"]
    world.conn.execute("UPDATE pending_changes SET created = created - 7200")
    world.conn.commit()
    assert "hour ago" in changes.confirm(world.state, world.conn, old, nonce)["error"] and open_window(world, old)["status"] == "expired"
    fresh = prepare(world)["data"]["change_id"]
    nonce = open_window(world, fresh)["nonce"]
    assert changes.cancel(world.conn, fresh)["ok"] and "already cancelled" in changes.confirm(world.state, world.conn, fresh, nonce)["error"]
    assert (world.photos / "receipt.jpg").exists() and audited(world, fresh)[-2:] == ["cancelled", "refused"]


def test_a_delete_goes_to_a_trash_folder_and_can_be_put_back_by_pressing_undo(world):
    change = prepare(world, "delete")["data"]["change_id"]
    window = open_window(world, change)
    assert "trash" in window["label"] and "Aperture - deleted" in window["into"]
    done = changes.confirm(world.state, world.conn, change, window["nonce"])
    assert done["ok"] and not (world.photos / "receipt.jpg").exists()
    assert any("Aperture - deleted" in str(p) for p in world.photos.rglob("receipt.jpg"))  # nothing is erased for good
    assert changes.undo(world.state, world.conn, "nonsense")["ok"] is False
    back = changes.undo(world.state, world.conn, done["batch"])
    assert back["ok"] and "put back 1" in back["text"] and (world.photos / "receipt.jpg").exists()
    assert audited(world, change)[-1] == "undone" and changes.overview(world.conn)["history"][0]["status"] == "undone"


def test_an_export_copies_and_leaves_the_originals(world):
    change = prepare(world, "export", folder="For the accountant")["data"]["change_id"]
    window = open_window(world, change)
    assert window["undo_number"] == "" and changes.confirm(world.state, world.conn, change, window["nonce"])["ok"]
    assert (world.photos / "receipt.jpg").exists() and any("accountant" in str(p) for p in world.engine.paths.drive.rglob("receipt.jpg"))


def test_nothing_is_prepared_for_a_request_that_matches_nothing_or_names_no_folder(world):
    assert tools.run(world.state, world.conn, "preview_delete_pictures", {"query": "zzzqqq"})["ok"] is False
    assert tools.run(world.state, world.conn, "preview_delete_pictures", {})["ok"] is False  # no filter: never "everything"
    assert tools.run(world.state, world.conn, "preview_move_pictures", {"query": "kassabon", "folder": ""})["ok"] is False
    assert world.conn.execute("SELECT COUNT(*) FROM pending_changes").fetchone()[0] == 0 and names(world.photos) == ["beach.jpg", "receipt.jpg"]


def test_a_folder_name_cannot_lead_outside_the_photo_folder(world):
    change = prepare(world, folder="../../etc")["data"]["change_id"]
    assert Path(open_window(world, change)["into"]).parent == world.photos  # reduced to one folder name directly inside the photo folder


def test_the_window_routes_serve_the_page_and_are_the_only_way_to_confirm(world):
    change = prepare(world)["data"]["change_id"]
    assert [c["id"] for c in web._get_changes(world.state, world.conn, {})["waiting"]] == [change]
    window = web._get_change(world.state, world.conn, {"id": change})
    assert window["nonce"] and web._post_confirm(world.state, world.conn, {"id": change, "nonce": window["nonce"]})["ok"] is True
    with pytest.raises(web.Fail):
        web._get_change(world.state, world.conn, {"id": "nonsense"})
    assert os.path.isfile(world.photos / "Receipts" / "receipt.jpg")


def test_whats_new_counts_new_documents_and_waiting_changes(world):
    out = tools.run(world.state, world.conn, "whats_new", {"days": "7"})
    assert out["ok"] and out["data"]["waiting_for_confirmation"] == []
    prepare(world)
    out = tools.run(world.state, world.conn, "whats_new", {})
    assert len(out["data"]["waiting_for_confirmation"]) == 1


def test_trip_albums_are_one_change_one_window_and_can_be_undone(world, monkeypatch):
    trip = {"title": "Goa", "place": "Goa", "start": "2000-01-01", "stop": "2100-01-01", "n": 2, "cover": 1}
    monkeypatch.setattr(changes.browse, "trips", lambda _conn: [trip])
    monkeypatch.setattr(changes, "MIN_TRIP_PHOTOS", 1)
    out = tools.run(world.state, world.conn, "preview_trip_albums", {})
    assert out["ok"] and out["items"][0]["kind"] == "confirm" and names(world.photos) == ["beach.jpg", "receipt.jpg"]  # nothing moved yet
    change = out["data"]["change_id"]
    window = open_window(world, change)
    assert window["problems"] == [] and {e["to"].split("/")[-2] for e in window["list"]} == {"2000 Goa"}
    done = changes.confirm(world.state, world.conn, change, window["nonce"])
    assert done["ok"] and (world.photos / "Trips" / "2000 Goa" / "beach.jpg").is_file()
    assert changes.undo(world.state, world.conn, done["batch"])["ok"] and (world.photos / "beach.jpg").is_file()


@pytest.fixture
def inbox(world, tmp_path, monkeypatch):
    """An inbox with an invoice, an insurance letter, a bank statement folder and one mail message, each already read into the store."""
    import hashlib
    import json

    root = tmp_path / "inbox"
    (root / "mail").mkdir(parents=True)
    monkeypatch.setenv("LIBRARY_INBOX", str(root))

    def add(path: Path, content: bytes, kind: str, area: str = "") -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        sha = hashlib.sha256(content).hexdigest()
        sha = hashlib.sha256((area + sha).encode()).hexdigest() if area else sha
        world.conn.execute(
            "INSERT INTO documents (sha256, name, kind, text, area, facts, judged, ready) VALUES (?,?,?,?,?,?,1,?)",
            (sha, path.name, "pdf", "t", area, json.dumps({"kind": kind}), world.conn.execute("SELECT COUNT(*)+1 FROM documents").fetchone()[0]),
        )
        return path

    world.invoice = add(root / "scan001.pdf", b"invoice", "invoice")
    world.letter = add(root / "letter.pdf", b"insurance", "insurance")
    world.mail = add(root / "mail" / "offer.eml", b"mail", "invoice", area="mail")
    world.root = root
    world.conn.commit()
    return world


def test_originals_are_filed_only_through_the_window_and_can_be_put_back(inbox):
    out = tools.run(inbox.state, inbox.conn, "preview_file_documents", {"kind": "invoice", "folder": "Invoices"})
    assert out["ok"] and out["data"]["files"] == 1 and inbox.invoice.is_file()  # nothing moved yet
    change = out["data"]["change_id"]
    window = open_window(inbox, change)
    assert window["problems"] == [] and window["list"][0]["to"].endswith("Invoices/scan001.pdf")
    done = changes.confirm(inbox.state, inbox.conn, change, window["nonce"])
    assert done["ok"] and (inbox.root / "Invoices" / "scan001.pdf").is_file() and not inbox.invoice.exists() and inbox.letter.is_file()
    assert changes.undo(inbox.state, inbox.conn, done["batch"])["ok"] and inbox.invoice.is_file()


def test_mail_is_copied_never_moved_and_the_mail_folder_is_never_a_destination(inbox):
    out = tools.run(inbox.state, inbox.conn, "preview_file_documents", {"folder": "Offers", "mail": True})
    change = out["data"]["change_id"]
    window = open_window(inbox, change)
    done = changes.confirm(inbox.state, inbox.conn, change, window["nonce"])
    assert done["ok"] and inbox.mail.is_file() and (inbox.root / "Filed mail" / "Offers" / "offer.eml").is_file()
    assert done["batch"] is None and changes.details(inbox.conn, inbox.state, change)["undo_number"] == ""  # a copy needs no undo: the original never moved
    assert filing.problems("file_move", [[1, str(inbox.invoice), str(inbox.root / "mail" / "x.pdf"), 7, 0]], str(inbox.root / "mail"))


def test_a_file_that_changed_or_a_missing_folder_name_stops_the_filing(inbox):
    assert not tools.run(inbox.state, inbox.conn, "preview_file_documents", {"kind": "invoice", "folder": ""})["ok"]
    out = tools.run(inbox.state, inbox.conn, "preview_file_documents", {"kind": "invoice", "folder": "Invoices"})
    inbox.invoice.write_bytes(b"changed after it was prepared")
    window = open_window(inbox, out["data"]["change_id"])
    assert any("changed since" in p for p in window["problems"])
    assert not changes.confirm(inbox.state, inbox.conn, out["data"]["change_id"], window["nonce"])["ok"] and inbox.invoice.is_file()


def test_documents_and_emails_are_listed_apart(inbox):
    names_of = lambda source: {d["name"] for d in store.list_documents(inbox.conn, ["invoice", "insurance"], source=source)}  # noqa: E731
    assert names_of("mail") == {"offer.eml"} and names_of("files") == {"scan001.pdf", "letter.pdf"}


def test_health_documents_go_only_to_whoever_asks_for_them_by_name(inbox):
    import json

    inbox.conn.execute(
        "INSERT INTO documents (sha256, name, kind, text, area, facts, judged, ready) VALUES ('h','blood.pdf','pdf','haemoglobin 14','',?,1,99)",
        (json.dumps({"kind": "medical"}),),
    )
    inbox.conn.commit()
    assert all(d["kind"] != "medical" for d in store.list_documents(inbox.conn, ["invoice"]))
    assert all(d["kind"] != "medical" for d in store.list_documents(inbox.conn, []))  # asking for everything does not include them
    assert [d["name"] for d in store.list_documents(inbox.conn, ["medical"])] == ["blood.pdf"]


def test_whole_library_pages_are_worked_out_once_per_change_to_the_library(world, monkeypatch):
    calls = []
    real = pictures.browsing.timeline
    monkeypatch.setattr(pictures.browsing, "timeline", lambda conn: calls.append(1) or real(conn))
    pictures.browse(world.engine, "timeline", {})
    pictures.browse(world.engine, "timeline", {})
    assert len(calls) == 1  # the second click used the first answer
    index = world.engine.db.connect()
    index.execute("UPDATE items SET missing=1 WHERE id=(SELECT MIN(id) FROM items)")
    index.commit()
    index.close()
    pictures.browse(world.engine, "timeline", {})
    assert len(calls) == 2  # a photo went missing: worked out again


def test_the_update_builds_the_search_index_so_the_first_question_does_not_wait(inbox):
    inbox.conn.execute("UPDATE documents SET judged=1, ready=1")
    inbox.conn.commit()
    assert store.warm_search(inbox.conn) >= 1  # the Update indexed what was read
    before = inbox.conn.execute("SELECT COUNT(*) FROM search_seen").fetchone()[0]
    assert before >= 1 and store.warm_search(inbox.conn) == 0  # nothing changed: nothing is read again
    store.passages(inbox.conn, "invoice")
    assert inbox.conn.execute("SELECT COUNT(*) FROM search_seen").fetchone()[0] == before  # the question found the index already built


def test_a_question_asked_while_the_index_is_being_built_does_not_wait_for_it(inbox):
    assert store._INDEXING.acquire(blocking=False)
    try:
        assert store.passages(inbox.conn, "invoice") == []  # uses what is there and does not start a second build
    finally:
        store._INDEXING.release()


def test_a_paused_update_waits_and_a_stopped_one_ends_without_losing_what_was_read(inbox, monkeypatch):
    inbox.conn.execute("UPDATE documents SET judged=0, facts='', ready=NULL")
    inbox.conn.commit()
    answers = iter(["pause", "pause", "run", "stop"])
    seen = []

    def control():
        seen.append(next(answers, "stop"))
        return seen[-1]

    monkeypatch.setattr(store.time, "sleep", lambda _s: None)  # no real waiting in the test
    out = store.judge_pending(inbox.conn, None, "", None, control)
    assert out["stopped"] is True and seen[:2] == ["pause", "pause"]  # it waited while paused, then ended when stopped
    assert inbox.conn.execute("SELECT COUNT(*) FROM documents WHERE judged=0").fetchone()[0] >= 1  # what was not read yet is still waiting


def test_the_reader_waits_while_paused_and_ends_the_round_when_stopped(tmp_path, monkeypatch):
    from library import parser

    monkeypatch.setattr(parser, "GENTLE_SECONDS", 0)
    out = tmp_path / "out"
    out.mkdir()
    (out / parser.PAUSE).touch()
    sleeps = []

    def sleep(_s):
        sleeps.append(1)
        (out / parser.PAUSE).unlink(missing_ok=True)  # the person presses Resume while it waits

    monkeypatch.setattr(parser.time, "sleep", sleep)
    assert parser.checkpoint(out) is False and sleeps  # it waited, then carried on
    (out / parser.STOP).touch()
    assert parser.checkpoint(out) is True  # stopped: the round ends at the next safe point


def test_tens_of_thousands_of_documents_are_judged_a_chunk_at_a_time_never_all_in_memory(inbox, monkeypatch):
    class Counting:
        """A connection that records how many rows each query handed back."""

        def __init__(self, conn):
            self.conn, self.biggest = conn, 0

        def execute(self, sql, *args):
            cur = self.conn.execute(sql, *args)
            if "FROM documents WHERE judged=0 AND id>?" in sql:
                rows = cur.fetchall()
                self.biggest = max(self.biggest, len(rows))
                return type("R", (), {"fetchall": lambda _s: rows})()
            return cur

        def commit(self):
            self.conn.commit()

    monkeypatch.setattr(store, "JUDGE_CHUNK", 2)
    monkeypatch.setattr(store, "GENTLE_SECONDS", 0)
    for i in range(7):
        inbox.conn.execute(
            "INSERT INTO documents (sha256, name, kind, text, area) VALUES (?,?,?,?,?)", (f"{i + 100:064x}", f"m{i}.eml", "email", f"mail {i}", "mail")
        )
    inbox.conn.execute("UPDATE documents SET judged=0, facts='', ready=NULL")
    inbox.conn.commit()
    total = inbox.conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    counting = Counting(inbox.conn)
    out = store.judge_pending(counting, None, "")
    assert counting.biggest <= 2 and out["read"] + out["skipped"] + out["waiting"] == total  # two at a time, every document accounted for
    inbox.conn.execute("UPDATE documents SET judged=0, facts='', ready=NULL")
    inbox.conn.commit()
    seen = iter(["run", "run", "run", "stop"])
    out = store.judge_pending(Counting(inbox.conn), None, "", None, lambda: next(seen, "stop"))
    assert out["stopped"] is True and out["waiting"] >= 1
