import numpy as np
from images import quality
from images.config import preview_rel
from images.similar import SimilarSettings, find_similar_groups
from PIL import Image, ImageFilter


def texture(seed=0, size=600):
    """Coarse light/dark structure (survives blur) plus fine detail (does not)."""
    rng = np.random.default_rng(seed)
    coarse = Image.fromarray(rng.integers(0, 255, (6, 6), dtype=np.uint8)).resize((size, size), Image.Resampling.NEAREST)
    fine = rng.integers(-40, 40, (size, size))
    return Image.fromarray(np.clip(np.asarray(coarse, dtype=int) + fine, 0, 255).astype(np.uint8))


def metrics(img):
    return quality.analyze_gray(np.asarray(img.convert("L").resize((512, 512))))


def test_blur_is_detected_and_sharp_is_not():
    sharp, blurred = metrics(texture()), metrics(texture().filter(ImageFilter.GaussianBlur(8)))
    assert blurred.sharp < sharp.sharp / 20
    assert quality.defect_reason(sharp) is None
    assert quality.defect_reason(blurred) == "blurry"


def test_sharp_subject_on_soft_background_is_not_blurry():
    img = texture().filter(ImageFilter.GaussianBlur(8))
    img.paste(texture(1, 200), (200, 200))
    assert quality.defect_reason(metrics(img)) is None


def test_exposure_and_blank_frames():
    assert quality.defect_reason(quality.Metrics(500, 10, 30)) == "too dark"
    assert quality.defect_reason(quality.Metrics(500, 245, 30)) == "too bright"
    assert quality.defect_reason(quality.Metrics(0, 120, 1)) == "blank or covered lens"
    assert quality.defect_reason(quality.Metrics(500, 120, 40)) is None


def test_sensitivity_changes_outcome():
    m = quality.Metrics(30, 120, 40)
    assert quality.defect_reason(m, "low") is None and quality.defect_reason(m, "high") == "blurry"


def test_best_of_prefers_sharp_well_exposed(scanned):
    conn = scanned.db.connect()
    ids = [r[0] for r in conn.execute("SELECT id FROM items ORDER BY id LIMIT 3")]
    for i, (sharp, bright) in zip(ids, [(20, 120), (400, 120), (400, 20)], strict=True):
        conn.execute("UPDATE items SET sharp=?, bright=?, contrast=40 WHERE id=?", (sharp, bright, i))
    assert quality.best_of(conn, ids) == ids[1]


def test_ensure_quality_and_labels_roundtrip(scanned):
    conn = scanned.db.connect()
    assert quality.ensure_quality(conn, scanned.paths) == 5
    assert quality.ensure_quality(conn, scanned.paths) == 0  # resumable: nothing left
    # solid-colour test photos have no texture: all suggested as blurry/blank
    suggestions = quality.suggest_defects(conn, "medium")
    assert len(suggestions) == 5
    quality.set_defects(conn, suggestions[:2])
    quality.mark_ok(conn, [suggestions[2][0]])
    assert len(quality.suggest_defects(conn)) == 2  # reviewed photos are not suggested again
    marked = quality.defect_ids(conn)
    assert len(marked) == 2 and set(quality.defect_reasons(conn, marked.tolist())) == set(marked.tolist())
    from images.library import item_ids

    assert len(item_ids(conn, hide_defects=True)) == 3 and len(item_ids(conn)) == 5
    quality.unmark(conn, marked.tolist())
    assert len(quality.defect_ids(conn)) == 0
    assert (scanned.paths.data / preview_rel(1)).exists()


def test_similar_groups_by_embedding_and_time(scanned):
    conn = scanned.db.connect()
    conn.execute("UPDATE items SET taken_at='2024-05-01 10:00:00'")
    conn.execute("UPDATE items SET taken_at='2024-05-01 18:00:00' WHERE path LIKE '%blue_1%'")
    conn.commit()
    index = scanned.embedding_index()
    groups = find_similar_groups(conn, index, SimilarSettings(threshold=0.9, window_minutes=30))
    sizes = sorted(len(g) for g in groups)
    assert sizes == [3]  # three reds together; blues are 8 hours apart, so not linked
    far = find_similar_groups(conn, index, SimilarSettings(threshold=0.9, window_minutes=24 * 60))
    assert sorted(len(g) for g in far) == [2, 3]
    assert find_similar_groups(conn, index, SimilarSettings(threshold=1.01)) == []
