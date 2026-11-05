from orbit import applenotes as an
from orbit.modules import notes, people

FAKE = [
    {
        "folder": "Trips",
        "id": "x-coredata://A/ICNote/p1",
        "title": "Packing list - Singapore",
        "locked": False,
        "created": "2024-03-01T09:00:00.000Z",
        "modified": "2024-03-02T10:30:00.000Z",
        "html": "<div><h1>Packing</h1></div><div>passport&nbsp;&amp; visa</div><ul><li>charger</li><li>adapter</li></ul>"
        "<div><img src='data:image/png;base64,AAAA'></div>",
    },
    {
        "folder": "../../etc",
        "id": "p2",
        "title": "Evil\nname: x",
        "locked": False,
        "created": "",
        "modified": "",
        "html": "<p>Ramesh BP tablet after breakfast</p>",
    },
    {"folder": "Private", "id": "p3", "title": "Secret", "locked": True, "html": ""},
]


def test_html_to_text():
    t = an.html_to_text(FAKE[0]["html"])
    assert "# Packing" in t and "passport & visa" in t and "- charger\n- adapter" in t
    assert "[attachment]" in t and "AAAA" not in t
    assert an.html_to_text("<script>x=1</script>hello") == "hello"


def test_write_skips_locked_and_stays_inside_dir(tmp_path):
    out = tmp_path / "notes"
    assert an.write_notes(FAKE, out) == {"exported": 2, "locked_skipped": 1}
    files = sorted(p.relative_to(out).as_posix() for p in out.rglob("*.md"))
    assert len(files) == 2 and all(not f.startswith("..") for f in files)
    assert not (tmp_path / "etc").exists()
    evil = next(out.rglob("evil-name-x-*.md")).read_text()
    assert evil.count("\ntitle: ") == 1 and "\nname: x" not in evil.split("---")[1].replace("title: Evil name: x", "")


def test_import_roundtrip_dedupes_and_updates(conn, tmp_path):
    people.add_person(conn, {"name": "Ramesh Kumar"})
    out = tmp_path / "notes"
    an.write_notes(FAKE, out)
    assert an.import_dir(conn, out) == {"new": 2, "updated": 0, "unchanged": 0, "skipped": 0}
    assert an.import_dir(conn, out) == {"new": 0, "updated": 0, "unchanged": 2, "skipped": 0}
    got = {n["title"]: n for n in notes.search_notes(conn, {})}
    sg = got["Packing list - Singapore"]
    assert sg["tags"] == "documents,travel,trips" and sg["created"] == "2024-03-01 09:00:00"
    assert "ramesh" in got["Evil name: x"]["tags"] and "health" in got["Evil name: x"]["tags"]
    # a change in Notes updates the existing row; user-set tags survive
    notes.update_note(conn, {"id": sg["id"], "tags": "mine"})
    changed = [{**FAKE[0], "html": "<div>new text</div>"}]
    an.write_notes(changed, out)
    assert an.import_dir(conn, out)["updated"] == 1
    again = notes.search_notes(conn, {"query": "new text"})[0]
    assert again["tags"] == "mine" and again["id"] == sg["id"]


def test_import_ignores_junk_and_symlinks(conn, tmp_path):
    out = tmp_path / "notes"
    out.mkdir()
    (out / "junk.md").write_text("no front matter")
    outside = tmp_path / "outside.md"
    outside.write_text("---\ntitle: t\nsource_id: s\n---\nbody\n")
    (out / "link.md").symlink_to(outside)
    assert an.import_dir(conn, out) == {"new": 0, "updated": 0, "unchanged": 0, "skipped": 2}


def test_export_needs_a_mac(monkeypatch):
    import pytest

    monkeypatch.setattr(an.sys, "platform", "linux")
    with pytest.raises(RuntimeError, match="macOS"):
        an.fetch_notes()
