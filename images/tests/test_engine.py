"""The engine works on its own, with no app next to it; and moving it did not move anyone's existing index."""

from images.engine import Engine


def test_an_existing_index_keeps_its_name_and_place(paths):
    assert (
        paths.db.name == "aperture.db" and paths.root.name == "Aperture"
    )  # the files already on a drive are found where they were


def test_the_engine_opens_its_database_and_scans_a_folder_with_injected_models(paths, monkeypatch):
    from PIL import Image

    from images.indexing.pipeline import Services
    from images.indexing.runner import Scanner

    photos = paths.drive / "Photos"
    photos.mkdir()
    Image.new("RGB", (40, 30), (200, 20, 20)).save(photos / "red.jpg")
    engine = Engine(paths)
    engine.settings.photo_dir = str(photos)
    summary = Scanner(engine.paths, engine.settings, engine.db, lambda stage: Services()).run()
    assert summary.state == "done" and engine.db.connect().execute("SELECT COUNT(*) FROM items").fetchone()[0] == 1


def test_the_index_is_encrypted_with_a_key_and_an_old_plain_index_is_converted_once(paths, monkeypatch):
    import sqlite3

    from images.db import Database

    plain = Database(paths.db)
    conn = plain.connect()
    conn.execute("INSERT INTO fts(rowid, text) VALUES (1, 'kassabon Albert Heijn')")
    conn.commit()
    conn.close()
    assert sqlite3.connect(paths.db).execute("SELECT count(*) FROM sqlite_master").fetchone()[0] > 0  # readable without a key

    monkeypatch.setenv("ORBIT_DB_KEY", "a-test-key")
    secured = Database(paths.db).connect()
    assert (
        secured.execute("SELECT rowid FROM fts WHERE fts MATCH 'kassabon'").fetchall()[0][0] == 1
    )  # the full-text index came along
    secured.close()
    with __import__("pytest").raises(sqlite3.DatabaseError):
        sqlite3.connect(paths.db).execute("SELECT count(*) FROM sqlite_master").fetchone()  # no longer readable without the key
    assert paths.db.with_name(paths.db.name + ".unencrypted").is_file()  # the old file is kept until you delete it


def test_pictures_from_more_than_one_folder_are_indexed_together(paths):
    from PIL import Image

    from images.indexing.pipeline import Services
    from images.indexing.runner import Scanner

    photos, inbox = paths.drive / "Photos", paths.drive / "Inbox"
    photos.mkdir()
    inbox.mkdir()
    Image.new("RGB", (40, 30), (200, 20, 20)).save(photos / "red.jpg")
    Image.new("RGB", (40, 30), (20, 20, 200)).save(inbox / "attachment.png")
    engine = Engine(paths)
    engine.settings.photo_dir = str(photos)
    engine.settings.extra_dirs = str(inbox)
    Scanner(engine.paths, engine.settings, engine.db, lambda stage: Services()).run()
    names = sorted(r[0] for r in engine.db.connect().execute("SELECT rel_path FROM items WHERE missing=0"))
    assert names == ["Inbox/attachment.png", "red.jpg"]  # a file from the other folder is named by that folder
