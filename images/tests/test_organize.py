import shutil
from pathlib import Path

import pytest

from conftest import fake_services
from images import organize
from images.indexing.runner import Scanner
from images.library import get_item, items_by_ids
from images.safety import SafetyError


@pytest.fixture
def dup_ctx(scanned, library):
    """The scanned library plus two byte-identical copies of a red photo."""
    src = library / "Holidays" / "Italy" / "red_0.jpg"
    (library / "Backup").mkdir()
    shutil.copy2(src, library / "Backup" / "red_0_copy.jpg")
    shutil.copy2(src, library / "Backup" / "red_0_copy2.jpg")
    Scanner(scanned.paths, scanned.settings, scanned.db, fake_services).run()
    scanned.settings.allow_moves = True
    return scanned


def groups(ctx):
    return organize.find_exact_duplicates(ctx.db.connect())


def test_finds_only_exact_duplicates(dup_ctx):
    found = groups(dup_ctx)
    assert len(found) == 1 and len(found[0]) == 3


def test_moves_disabled_by_default(scanned):
    conn = scanned.db.connect()
    plan = organize.plan_move(conn, scanned.paths, _enable(scanned), [1], Path(scanned.settings.photo_dir) / "x")
    scanned.settings.allow_moves = False
    with pytest.raises(SafetyError):
        organize.execute_move(conn, scanned.paths, scanned.settings, plan, "nope")


def _enable(ctx):
    ctx.settings.allow_moves = True
    return ctx.settings


def test_keeper_rules(dup_ctx):
    conn = dup_ctx.db.connect()
    items = list(items_by_ids(conn, groups(dup_ctx)[0]).values())
    assert organize.choose_keeper(items, "shortest_path") == min(items, key=lambda i: (len(i.rel_path), i.id)).id
    assert organize.choose_keeper(items, "oldest") in {i.id for i in items}


def test_move_and_undo_roundtrip(dup_ctx):
    conn = dup_ctx.db.connect()
    s, p = dup_ctx.settings, dup_ctx.paths
    group = groups(dup_ctx)
    keep = organize.choose_keeper(list(items_by_ids(conn, group[0]).values()), "shortest_path")
    dest = Path(s.photo_dir) / "Dupes"
    plan = organize.plan_duplicate_moves(conn, p, s, group, {0: keep}, dest)
    assert plan.count == 2
    before = {e.src: Path(e.src).read_bytes() for e in plan.entries}
    report = organize.execute_move(conn, p, s, plan, "test")
    assert report.moved == 2 and not report.failed
    for e in plan.entries:
        assert not Path(e.src).exists() and Path(e.dst).read_bytes() == before[e.src]
        assert get_item(conn, e.item_id).path == e.dst
    assert Path(get_item(conn, keep).path).exists()  # keeper untouched

    undone = organize.undo_batch(conn, p, s, report.batch)
    assert undone.moved == 2 and not undone.failed
    for e in plan.entries:
        assert Path(e.src).read_bytes() == before[e.src] and get_item(conn, e.item_id).path == e.src
    assert organize.list_batches(conn)[0].undone


def test_never_overwrites_and_refuses_outside_library(dup_ctx, tmp_path):
    conn = dup_ctx.db.connect()
    s, p = dup_ctx.settings, dup_ctx.paths
    with pytest.raises(SafetyError):
        organize.plan_move(conn, p, s, [1], tmp_path / "elsewhere")
    with pytest.raises(SafetyError):
        organize.plan_move(conn, p, s, [1], s.photo_dir)
    ids = [r[0] for r in conn.execute("SELECT id FROM items LIMIT 2")]
    plan = organize.plan_move(conn, p, s, ids, Path(s.photo_dir) / "Pile", keep_structure=False)
    taken = Path(plan.entries[0].dst)
    taken.parent.mkdir(parents=True)
    taken.write_bytes(b"precious")
    report = organize.execute_move(conn, p, s, plan, "clash")
    assert taken.read_bytes() == b"precious" and report.failed


def test_index_follows_moved_files(dup_ctx):
    conn = dup_ctx.db.connect()
    s, p = dup_ctx.settings, dup_ctx.paths
    ids = [r[0] for r in conn.execute("SELECT id FROM items WHERE kind='image' LIMIT 1")]
    plan = organize.plan_move(conn, p, s, ids, Path(s.photo_dir) / "Moved")
    organize.execute_move(conn, p, s, plan, "x")
    Scanner(p, s, dup_ctx.db, fake_services).run()
    row = conn.execute("SELECT missing, clip_done FROM items WHERE id=?", (ids[0],)).fetchone()
    assert row["missing"] == 0 and row["clip_done"] == 1  # same item, not re-indexed
