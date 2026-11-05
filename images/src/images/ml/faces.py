"""Face detection (SCRFD) and recognition (ArcFace) on onnxruntime.

Uses the ``buffalo_l`` ONNX models directly instead of the ``insightface``
package, which needs a C compiler on macOS and is the most common source of
installation failures.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .protocols import DetectedFace

# Canonical 5-point template of a 112x112 ArcFace-aligned face.
ARCFACE_TEMPLATE = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float32,
)
STRIDES = (8, 16, 32)


def similarity_transform(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Umeyama least-squares similarity transform as a 2x3 affine matrix."""
    n = src.shape[0]
    mu_s, mu_d = src.mean(0), dst.mean(0)
    s0, d0 = src - mu_s, dst - mu_d
    var_s = (s0**2).sum() / n
    cov = d0.T @ s0 / n
    u, s, vt = np.linalg.svd(cov)
    sign = np.ones(2)
    if np.linalg.det(cov) < 0:
        sign[-1] = -1
    rot = u @ np.diag(sign) @ vt
    scale = (s * sign).sum() / var_s
    shift = mu_d - scale * (rot @ mu_s)
    return np.hstack([scale * rot, shift[:, None]]).astype(np.float32)


def non_max_suppression(boxes: np.ndarray, scores: np.ndarray, threshold: float) -> list[int]:
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep: list[int] = []
    while order.size:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        xx1, yy1 = np.maximum(x1[i], x1[rest]), np.maximum(y1[i], y1[rest])
        xx2, yy2 = np.minimum(x2[i], x2[rest]), np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, xx2 - xx1 + 1) * np.maximum(0.0, yy2 - yy1 + 1)
        iou = inter / (areas[i] + areas[rest] - inter)
        order = rest[iou <= threshold]
    return keep


def _keypoints(anchors: np.ndarray, distances: np.ndarray) -> np.ndarray:
    cols = []
    for i in range(0, 10, 2):
        cols.append(anchors[:, 0] + distances[:, i])
        cols.append(anchors[:, 1] + distances[:, i + 1])
    return np.stack(cols, axis=1)


class OnnxFaceAnalyzer:
    """:class:`~images.ml.protocols.FaceAnalyzer` backed by onnxruntime."""

    def __init__(
        self,
        model_dir: Path,
        *,
        det_size: int = 640,
        det_thresh: float = 0.5,
        use_coreml: bool = False,
    ) -> None:
        import cv2
        import onnxruntime as ort

        det_path, rec_path = model_dir / "det_10g.onnx", model_dir / "w600k_r50.onnx"
        if not det_path.exists() or not rec_path.exists():
            raise FileNotFoundError(f"Face models missing in {model_dir}. Run: aperture fetch-models")
        self._cv2 = cv2
        self._size = det_size
        self._thresh = det_thresh
        providers = ["CPUExecutionProvider"]
        if use_coreml and "CoreMLExecutionProvider" in ort.get_available_providers():
            providers.insert(0, "CoreMLExecutionProvider")
        options = ort.SessionOptions()
        options.log_severity_level = 3
        options.intra_op_num_threads = 2  # several photos are analysed in parallel
        self._det = ort.InferenceSession(str(det_path), options, providers=providers)
        self._rec = ort.InferenceSession(str(rec_path), options, providers=providers)
        self._det_in = self._det.get_inputs()[0].name
        self._det_out = [o.name for o in self._det.get_outputs()]
        self._rec_in = self._rec.get_inputs()[0].name

    # ------------------------------------------------------------------
    def analyse(self, bgr: np.ndarray) -> list[DetectedFace]:
        detections = self._detect(bgr)
        if not detections:
            return []
        embeddings = self._embed(bgr, [kps for _, _, kps in detections])
        return [
            DetectedFace(
                bbox=(float(b[0]), float(b[1]), float(b[2]), float(b[3])),
                score=score,
                embedding=emb,
            )
            for (b, score, _), emb in zip(detections, embeddings, strict=True)
        ]

    def _detect(self, bgr: np.ndarray) -> list[tuple[np.ndarray, float, np.ndarray]]:
        cv2, size = self._cv2, self._size
        h, w = bgr.shape[:2]
        ratio = h / w
        new_h, new_w = (size, max(1, int(size / ratio))) if ratio > 1 else (max(1, int(size * ratio)), size)
        scale = new_h / h
        canvas = np.zeros((size, size, 3), np.uint8)
        canvas[:new_h, :new_w] = cv2.resize(bgr, (new_w, new_h))
        blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128, (size, size), (127.5, 127.5, 127.5), swapRB=True)
        outputs = self._det.run(self._det_out, {self._det_in: blob})

        boxes, scores, points = [], [], []
        for idx, stride in enumerate(STRIDES):
            score = np.asarray(outputs[idx]).reshape(-1)
            box_d = np.asarray(outputs[idx + 3]).reshape(-1, 4) * stride
            kps_d = np.asarray(outputs[idx + 6]).reshape(-1, 10) * stride
            cells = size // stride
            anchors = np.stack(np.mgrid[:cells, :cells][::-1], axis=-1).astype(np.float32).reshape(-1, 2) * stride
            anchors = np.stack([anchors] * 2, axis=1).reshape(-1, 2)  # two anchors per cell
            keep = np.where(score >= self._thresh)[0]
            if not keep.size:
                continue
            a, b, k = anchors[keep], box_d[keep], kps_d[keep]
            boxes.append(np.stack([a[:, 0] - b[:, 0], a[:, 1] - b[:, 1], a[:, 0] + b[:, 2], a[:, 1] + b[:, 3]], 1))
            points.append(_keypoints(a, k))
            scores.append(score[keep])
        if not boxes:
            return []
        all_boxes = np.vstack(boxes) / scale
        all_scores = np.concatenate(scores)
        all_points = np.vstack(points) / scale
        keep_idx = non_max_suppression(all_boxes, all_scores, 0.4)
        return [(all_boxes[i], float(all_scores[i]), all_points[i].reshape(5, 2)) for i in keep_idx]

    def _embed(self, bgr: np.ndarray, keypoints: list[np.ndarray]) -> np.ndarray:
        cv2 = self._cv2
        crops = []
        for kps in keypoints:
            matrix = similarity_transform(kps.astype(np.float32), ARCFACE_TEMPLATE)
            crops.append(cv2.warpAffine(bgr, matrix, (112, 112), borderValue=0.0))
        blob = cv2.dnn.blobFromImages(crops, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=True)
        feats = self._rec.run(None, {self._rec_in: blob})[0].astype(np.float32)
        return feats / np.linalg.norm(feats, axis=1, keepdims=True)
