"""Moving, deleting, exporting and undoing the person's own pictures: prepared first, done only by a later question whose own words confirm it, always undoable."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from images import organize
from images.config import ENV_INTERNAL
from kit import db
from PIL import Image

from library import indexer, pictures, store, tools
from tests.test_pictures import FakeOCR, engine_with_fake_models  # noqa: F401


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv(ENV_INTERNAL, "1")
    monkeypatch.setenv("LIBRARY_PICTURES_DRIVE", str(tmp_path / "drive"))
    monkeypatch.setenv("LIBRARY_PHOTOS", str(tmp_path / "drive" / "Photos"))
    photos = tmp_path / "drive" / "Photos"
    photos.mkdir(parents=True)
    Image.new("RGB", (120, 100), (220, 20, 20)).save(photos / "receipt.jpg")  # the fake reader finds text in red pictures
    Image.new("RGB", (120, 100), (20, 20, 220)).save(photos / "beach.jpg")
    engine = engine_with_fake_models()
    indexer.run_once(engine)
    conn = db.connect(tmp_path / "library.db")
    db.migrate(conn, [store.MODULE])
    return SimpleNamespace(engine=engine, conn=conn, state=SimpleNamespace(engine=lambda: engine, picture_text=lambda: None), photos=photos)


def run(w, name, args, text="", turn="t1"):
    return tools.run(w.state, w.conn, name, args, tools.Ask(text, turn))


def names(folder):
    return sorted(p.name for p in folder.rglob("*") if p.is_file())


def test_a_move_is_prepared_then_confirmed_in_a_later_question_and_changes_only_what_was_described(world):
    prepared = run(world, "preview_move_pictures", {"query": "kassabon", "folder": "Receipts"}, "move the receipts to Receipts", "t1")
    data = prepared["data"]
    assert prepared["ok"] and data["will_move"] == 1 and data["examples"] == ["receipt.jpg"] and "NOT DONE YET" in data["status"]
    assert names(world.photos) == ["beach.jpg", "receipt.jpg"]  # nothing has moved
    same_turn = run(world, "apply_change", {"change_id": data["change_id"]}, "yes", "t1")
    assert same_turn["data"]["ok"] is False and "same question" in same_turn["data"]["error"]  # the model cannot confirm its own preparation
    unconfirmed = run(world, "apply_change", {"change_id": data["change_id"]}, "hmm, what would that do?", "t2")
    assert unconfirmed["data"]["ok"] is False and "not confirmed" in unconfirmed["data"]["error"]
    done = run(world, "apply_change", {"change_id": data["change_id"]}, "yes, go ahead", "t2")["data"]
    assert done["done"] is True and done["moved"] == 1 and done["undo_number"]
    assert (world.photos / "Receipts" / "receipt.jpg").is_file() and not (world.photos / "receipt.jpg").exists() and (world.photos / "beach.jpg").is_file()
    again = run(world, "apply_change", {"change_id": data["change_id"]}, "yes", "t3")
    assert again["data"]["ok"] is False and "already" in again["data"]["error"]
    index = world.engine.db.connect()
    assert index.execute("SELECT rel_path FROM items WHERE rel_path LIKE '%receipt%'").fetchone()[0] == "Receipts/receipt.jpg"  # the index followed the file


def test_an_undo_needs_the_persons_words_and_puts_everything_back(world):
    change = run(world, "preview_move_pictures", {"query": "kassabon", "folder": "Receipts"}, "move them", "t1")["data"]["change_id"]
    batch = run(world, "apply_change", {"change_id": change}, "yes", "t2")["data"]["undo_number"]
    assert run(world, "undo_change", {"undo_number": batch}, "ok", "t3")["data"]["ok"] is False  # "ok" confirms a change, it does not undo one
    back = run(world, "undo_change", {"undo_number": batch}, "undo that", "t3")["data"]
    assert back["restored"] == 1 and (world.photos / "receipt.jpg").is_file() and not (world.photos / "Receipts" / "receipt.jpg").exists()
    listed = run(world, "list_changes", {}, "", "t4")["data"]["changes"]
    assert listed[0]["undo_number"] == batch and listed[0]["undone"] is True


def test_a_delete_moves_the_picture_to_a_trash_folder_so_it_can_be_undone(world):
    prepared = run(world, "preview_delete_pictures", {"query": "kassabon"}, "delete the receipt photo", "t1")["data"]
    assert prepared["kind"] == "delete" and "Aperture - deleted" in prepared["into"] and (world.photos / "receipt.jpg").exists()
    done = run(world, "apply_change", {"change_id": prepared["change_id"]}, "yes delete it", "t2")["data"]
    assert done["moved"] == 1 and not (world.photos / "receipt.jpg").exists()
    assert any("Aperture - deleted" in str(p) for p in world.photos.rglob("receipt.jpg"))  # nothing is erased for good
    assert (
        run(world, "undo_change", {"undo_number": done["undo_number"]}, "put it back", "t3")["data"]["restored"] == 1
        and (world.photos / "receipt.jpg").exists()
    )


def test_nothing_is_prepared_for_a_request_that_matches_nothing_or_names_no_folder(world):
    assert run(world, "preview_delete_pictures", {"query": "zzzqqq"})["ok"] is False
    assert run(world, "preview_delete_pictures", {})["ok"] is False  # no filter: never "everything"
    assert run(world, "preview_move_pictures", {"query": "kassabon", "folder": ""})["ok"] is False
    assert names(world.photos) == ["beach.jpg", "receipt.jpg"]


def test_a_folder_name_cannot_lead_outside_the_photo_folder(world):
    prepared = run(world, "preview_move_pictures", {"query": "kassabon", "folder": "../../etc"})
    assert prepared["ok"] is True and Path(prepared["data"]["into"]).parent == world.photos  # reduced to one folder name directly inside the photo folder


def test_no_change_is_made_while_the_indexer_is_running(world):
    change = run(world, "preview_move_pictures", {"query": "kassabon", "folder": "Receipts"}, "move", "t1")["data"]["change_id"]
    pictures.write_state(world.engine, True, "Reading pictures…")
    blocked = run(world, "apply_change", {"change_id": change}, "yes", "t2")["data"]
    assert blocked["ok"] is False and "Indexing is running" in blocked["error"] and (world.photos / "receipt.jpg").exists()
    pictures.write_state(world.engine, False)
    assert run(world, "apply_change", {"change_id": change}, "yes", "t2")["data"]["done"] is True


def test_an_old_prepared_change_expires(world, monkeypatch):
    change = run(world, "preview_move_pictures", {"query": "kassabon", "folder": "Receipts"}, "move", "t1")["data"]["change_id"]
    world.conn.execute("UPDATE pending_changes SET created = created - 7200")
    world.conn.commit()
    assert "hour ago" in run(world, "apply_change", {"change_id": change}, "yes", "t2")["data"]["error"]


def test_exporting_copies_and_never_moves(world, monkeypatch):
    copied = run(world, "export_pictures", {"query": "kassabon", "folder": "For the accountant"})["data"]
    assert copied["copied"] == 1 and (world.photos / "receipt.jpg").exists()  # the original is still where it was
    assert any(p.name == "receipt.jpg" for p in world.engine.paths.drive.rglob("*") if "accountant" in str(p))


def test_the_move_code_is_the_journaled_one(world):
    assert hasattr(organize, "execute_move") and hasattr(organize, "undo_batch")
