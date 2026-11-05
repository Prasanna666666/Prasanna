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
