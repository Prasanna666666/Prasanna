"""A place recogniser learned from the library's own photos.

The photos that have GPS are the teacher: for any other photo the model combines
  1. how similar its picture is to photos of each known place (nearest neighbours in the image-embedding space, ignoring photos taken
     within 30 minutes of it, so a burst of the same scene cannot make the test look easier than it is),
  2. which place the photos taken around the same time were in,
into a probability per place. The probabilities are checked on photos whose true place is known (they are hidden, predicted, compared), and a
photo is given a location only above the probability that measured at least `min_precision` accurate. Everything else stays unlocated.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np

from .derive import MIN_PRECISION

CELL_DEG = 0.25  # about 25 km: a "place" for this model is a 0.25 x 0.25 degree cell
K_NEIGHBOURS = 20
EXCLUDE_MIN = (
    24 * 60.0
)  # visual neighbours taken within a day of the photo are ignored: the picture must be recognised from OTHER occasions
TIME_WINDOW_MIN = 12 * 60.0
TIME_SCALE_MIN = 60.0
MAX_TEST = 20000
MIN_TESTS_PER_PLACE = 8  # a place must have been tested at least this often to be trusted
CHUNK = 512
MIN_GPS_PHOTOS = 200  # fewer photos with a place than this teach nothing
MIN_CHECKED = 100  # a check needs this many photos to mean anything
NEAREST_IN_TIME = 40  # the closest photos in time that are compared


def _cell(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    return (np.floor(lat / CELL_DEG).astype(np.int64) + 1000) * 100000 + (np.floor(lon / CELL_DEG).astype(np.int64) + 1000)


def _features(
    sims: np.ndarray,
    nb_cells: np.ndarray,
    q_times: np.ndarray,
    t_gps: np.ndarray,
    cell_gps: np.ndarray,
    self_pos: np.ndarray | None,
):
    """Per query: candidate cells and their feature rows [visual vote, best similarity, time vote]."""
    out = []
    for r in range(len(sims)):
        s = sims[r]
        vote: dict[int, float] = {}
        best: dict[int, float] = {}
        top = s.max()
        weights = np.exp(15.0 * (s - top))
        total = weights.sum() or 1.0
        for w, sim, c in zip(weights, s, nb_cells[r], strict=False):
            vote[int(c)] = vote.get(int(c), 0.0) + float(w) / total
            best[int(c)] = max(best.get(int(c), -1.0), float(sim))
        time_vote: dict[int, float] = {}
        t = q_times[r]
        if not np.isnan(t):
            lo, hi = np.searchsorted(t_gps, [t - TIME_WINDOW_MIN, t + TIME_WINDOW_MIN])
            idx = np.arange(max(lo, 0), hi)
            if self_pos is not None:
                idx = idx[idx != self_pos[r]]
            if len(idx) > NEAREST_IN_TIME:
                idx = idx[np.argsort(np.abs(t_gps[idx] - t))[:NEAREST_IN_TIME]]
            wt = np.exp(-np.abs(t_gps[idx] - t) / TIME_SCALE_MIN)
            tot = wt.sum()
            if tot > 0:
                for w, c in zip(wt, cell_gps[idx], strict=False):
                    time_vote[int(c)] = time_vote.get(int(c), 0.0) + float(w) / tot
        cells = sorted(set(vote) | set(time_vote))
        out.append((cells, np.array([[vote.get(c, 0.0), best.get(c, 0.0), time_vote.get(c, 0.0)] for c in cells], np.float64)))
    return out


def _fit(x: np.ndarray, y: np.ndarray, steps: int = 400, lr: float = 0.5) -> np.ndarray:
    """Logistic regression by gradient descent (a few features: no extra library needed)."""
    xb = np.hstack([x, np.ones((len(x), 1))])
    w = np.zeros(xb.shape[1])
    for _ in range(steps):
        p = 1.0 / (1.0 + np.exp(-np.clip(xb @ w, -30, 30)))
        w -= lr * (xb.T @ (p - y)) / len(y)
    return w


def _predict(w: np.ndarray, x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(np.hstack([x, np.ones((len(x), 1))]) @ w, -30, 30)))


def _top(candidates, w):
    """Best cell, its probability and how closely the picture matched known photos of it, for each query."""
    result = []
    for cells, feats in candidates:
        if not cells:
            result.append((None, 0.0, 0.0))
            continue
        p = _predict(w, feats)
        k = int(np.argmax(p))
        result.append((cells[k], float(p[k]), float(feats[k, 1])))
    return result


def _photo_table(conn: sqlite3.Connection, index: Any) -> tuple[dict[int, int], tuple[np.ndarray, ...]]:
    """The photos that have a picture vector, as parallel arrays: id, time (minutes), GPS, whether a location was estimated, and the estimate."""
    rows = conn.execute(
        "SELECT id, taken_at, gps_lat, gps_lon, gps_est_lat, gps_est_lon FROM items WHERE missing=0 AND meta_done=1"
    ).fetchall()
    row_of = {int(i): r for r, i in enumerate(index.ids.tolist())}
    ids, times, lat, lon, est, elat, elon = [], [], [], [], [], [], []
    for item_id, taken, la, lo, e, eo in rows:
        if item_id not in row_of:
            continue
        try:
            t = datetime.fromisoformat(str(taken)[:19]).timestamp() / 60.0
        except ValueError:
            t = np.nan
        ids.append(item_id)
        times.append(t)
        lat.append(np.nan if la is None else la)
        lon.append(np.nan if lo is None else lo)
        est.append(e is not None)
        elat.append(np.nan if e is None else e)
        elon.append(np.nan if eo is None else eo)
    arrays = (
        np.array(ids, np.int64),
        np.array(times, float),
        np.array(lat, float),
        np.array(lon, float),
        np.array(est, bool),
        np.array(elat, float),
        np.array(elon, float),
    )
    return row_of, arrays


def _trusted_places(predicted: np.ndarray, accepted: np.ndarray, ok: np.ndarray, min_precision: float) -> set[int]:
    """The places the model has earned the right to name: enough tests there, and the measured precision held up in that place alone."""
    trusted: set[int] = set()
    for cell in {c for c in predicted[accepted] if c is not None}:
        m = accepted & (predicted == cell)
        if m.sum() >= MIN_TESTS_PER_PLACE and ok[m].mean() >= min_precision:
            trusted.add(int(cell))
    return trusted


def _centroids(cells: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> dict[int, tuple[float, float]]:
    """The middle of each place, from the photos that really have GPS."""
    return {int(cell): (float(lat[cells == cell].mean()), float(lon[cells == cell].mean())) for cell in np.unique(cells)}


@dataclass
class _Photos:
    """The photo library as arrays, and the photos with GPS (in time order) that a prediction is made from."""

    ids: np.ndarray
    times: np.ndarray
    lat: np.ndarray
    lon: np.ndarray
    has: np.ndarray  # has GPS
    est: np.ndarray  # has an estimated place
    elat: np.ndarray
    elon: np.ndarray
    vec: np.ndarray  # what each photo looks like, normalised
    g_idx: np.ndarray  # the photos with GPS and a time, in time order
    gvec: np.ndarray
    tg: np.ndarray
    cells: np.ndarray  # the place (cell) of each of those


@dataclass
class _Accept:
    """When a prediction is taken: probability at least `threshold`, looks at least `floor` like its place, and a place the model `trusted` earned the right to name."""

    threshold: float
    floor: float
    trusted: set[int]
    precision: float

    def takes(self, cell, p: float, look: float) -> bool:
        return cell is not None and p >= self.threshold and look >= self.floor and int(cell) in self.trusted


def _photos(index: Any, row_of: dict, arrays: tuple) -> _Photos:
    ids, times, lat, lon, est, elat, elon = arrays
    has = ~np.isnan(lat)
    vec = index.vectors[[row_of[int(i)] for i in ids]].astype(np.float32)
    vec /= np.maximum(np.linalg.norm(vec, axis=1, keepdims=True), 1e-9)
    g_idx = np.flatnonzero(has & ~np.isnan(times))  # GPS photos with a time, in time order
    g_idx = g_idx[np.argsort(times[g_idx])]
    return _Photos(
        ids, times, lat, lon, has, est, elat, elon, vec, g_idx, vec[g_idx], times[g_idx], _cell(lat[g_idx], lon[g_idx])
    )


def _neighbours(p: _Photos, qvec: np.ndarray, qtimes: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For each query photo, how alike its closest GPS photos look and where they were taken (not counting photos from the same moment)."""
    sims_all, cells_all = [], []
    for start in range(0, len(qvec), CHUNK):
        block = qvec[start : start + CHUNK] @ p.gvec.T
        tq = qtimes[start : start + CHUNK]
        near_in_time = np.abs(p.tg[None, :] - np.nan_to_num(tq, nan=-1e12)[:, None]) <= EXCLUDE_MIN
        block[near_in_time] = -1.0  # the same moment says nothing new; also hides the photo itself
        top = np.argpartition(-block, K_NEIGHBOURS, axis=1)[:, :K_NEIGHBOURS]
        sims_all.append(np.take_along_axis(block, top, axis=1))
        cells_all.append(p.cells[top])
    return np.vstack(sims_all), np.vstack(cells_all)


def _predict_for(p: _Photos, rows: np.ndarray, w: np.ndarray, qtimes: np.ndarray | None = None) -> list:
    """The model's pick (cell, probability, how alike) for the photos at `rows`."""
    times = p.times[rows] if qtimes is None else qtimes
    s, c = _neighbours(p, p.vec[rows], times)
    return _top(_features(s, c, times, p.tg, p.cells, None), w)


def _hold_out(p: _Photos, seed: int):
    """Hide GPS photos, predict their cell and compare with the truth: the first half trains the model, the other half measures it. None when there is nothing to train on."""
    rng = np.random.default_rng(seed)
    test_pos = rng.permutation(len(p.g_idx))[:MAX_TEST]
    s, c = _neighbours(p, p.gvec[test_pos], p.tg[test_pos])
    cand = _features(s, c, p.tg[test_pos], p.tg, p.cells, test_pos)
    truth = p.cells[test_pos]
    half = len(test_pos) // 2
    xs, ys = [], []
    for (cs, f), t in zip(cand[:half], truth[:half], strict=False):
        for ci, fi in zip(cs, f, strict=False):
            xs.append(fi)
            ys.append(1.0 if ci == t else 0.0)
    if not xs:
        return None
    w = _fit(np.array(xs), np.array(ys))
    return w, _top(cand[half:], w), truth[half:]


def _measure(scored: list, truth: np.ndarray, min_precision: float, min_accepted: int, report: dict) -> _Accept | None:
    """From the held-out photos: the probability above which the measured precision holds, the places trusted, and how alike a photo must look. None when no probability is good enough."""
    ok = np.array([cell == t for (cell, _, _), t in zip(scored, truth, strict=False)])
    prob = np.array([p for _, p, _ in scored])
    looks = np.array([s for _, _, s in scored])
    order = np.argsort(-prob)
    cum_precision = np.cumsum(ok[order]) / (np.arange(len(order)) + 1)
    good = np.flatnonzero((cum_precision >= min_precision) & (np.arange(len(order)) + 1 >= min_accepted))
    report["tested"] = len(scored)
    if len(good) == 0:
        return None
    cut = int(good[-1])  # the most photos that still keep the measured precision
    threshold = float(prob[order][cut])
    precision = float(cum_precision[cut])
    # Accuracy per place, not only overall: home dominates the library and is easy; a rarer place has to earn its own 95%.
    predicted = np.array([c for c, _, _ in scored], dtype=object)
    trusted = _trusted_places(predicted, prob >= threshold, ok, min_precision)
    report["trusted_places"] = len(trusted)
    # a picture that matches known photos of its place much less closely than the correctly placed test photos did is out of its depth
    floor = float(np.percentile(looks[ok], 10)) if ok.any() else 1.0
    report.update(
        threshold=round(threshold, 3),
        accuracy_at_threshold=round(precision, 3),
        accepted_in_test=int(cut + 1),
        similarity_floor=round(floor, 3),
    )
    return _Accept(threshold, floor, trusted, precision)


def _agrees_with_estimates(p: _Photos, w: np.ndarray, accept: _Accept, min_precision: float, report: dict) -> bool:
    """The test photos have GPS, the photos to place do not, and they may look different (screenshots, forwarded pictures, other cameras). So also check the model on photos that have
    NO GPS but were located by time at >= 95%: if it disagrees with them, it places nothing. False means blocked."""
    checked = np.flatnonzero(~p.has & p.est & ~np.isnan(p.elat))
    if len(checked) < MIN_CHECKED:
        return True
    picks = _predict_for(p, checked, w)
    verdicts = [
        cell == t
        for (cell, pr, look), t in zip(picks, _cell(p.elat[checked], p.elon[checked]), strict=False)
        if accept.takes(cell, pr, look)
    ]
    if len(verdicts) < MIN_CHECKED:
        return True
    agreement = float(np.mean(verdicts))
    report.update(checked_on_no_gps=len(verdicts), agreement_on_no_gps=round(agreement, 3))
    if agreement < min_precision:
        report["blocked"] = True  # right on photos with GPS, wrong on photos like the ones to place: not trusted
        return False
    return True


def _place_the_rest(conn: sqlite3.Connection, p: _Photos, w: np.ndarray, accept: _Accept, geo: Any) -> int:
    """Estimate the place of the photos that have no GPS and no estimate yet; returns how many were placed."""
    q = np.flatnonzero(~p.has & ~p.est)
    if len(q) == 0:
        return 0
    centroid = _centroids(p.cells, p.lat[p.g_idx], p.lon[p.g_idx])
    updates = []
    for start in range(0, len(q), PLACE_BATCH):
        part = q[start : start + PLACE_BATCH]
        for item, (cell, pr, look) in zip(p.ids[part], _predict_for(p, part, w), strict=False):
            if accept.takes(cell, pr, look):
                la, lo = centroid[cell]
                place = geo.lookup(la, lo) if geo is not None else None
                updates.append(
                    (la, lo, accept.precision, place.label if place else None, place.search_text if place else "", int(item))
                )
    conn.executemany(
        "UPDATE items SET gps_est_lat=?, gps_est_lon=?, gps_est_conf=?, gps_est_place=?, gps_est_place_text=? WHERE id=?", updates
    )
    conn.commit()
    return len(updates)


PLACE_BATCH = 4096  # photos placed per step, so the memory stays small


def locate_by_picture(
    conn: sqlite3.Connection, index: Any, geo: Any, min_precision: float = MIN_PRECISION, min_accepted: int = 30, seed: int = 7
) -> dict:
    """Place photos that have no GPS by what they look like: measure on hidden GPS photos how reliable a guess is, and take only the guesses that keep the precision."""
    row_of, arrays = _photo_table(conn, index)
    has = ~np.isnan(arrays[2])
    report: dict[str, Any] = {
        "tested": 0,
        "accuracy_at_threshold": 0.0,
        "threshold": None,
        "located": 0,
        "without_gps": int((~has & ~arrays[4]).sum()),
    }
    if has.sum() < MIN_GPS_PHOTOS:
        return report
    p = _photos(index, row_of, arrays)
    held_out = _hold_out(p, seed)
    if held_out is None:
        return report
    w, scored, truth = held_out
    accept = _measure(scored, truth, min_precision, min_accepted, report)
    if accept is None or not _agrees_with_estimates(p, w, accept, min_precision, report):
        return report
    report["located"] = _place_the_rest(conn, p, w, accept, geo)
    return report
