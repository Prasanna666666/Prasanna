"""Everything Apple's Vision framework can say about a picture, on this Mac, with no model download.

Scene and object labels, animals and people with boxes, text with boxes, barcodes and the regions that draw the eye. Boxes are
normalised to 0..1 with the origin at the top left.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Details:
    labels: list[tuple[str, float]] = field(default_factory=list)
    objects: list[tuple[str, str, float, tuple[float, float, float, float]]] = field(default_factory=list)  # kind, label, score, box
    texts: list[tuple[str, float, tuple[float, float, float, float]]] = field(default_factory=list)


def to_box(rect: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Vision boxes are (x, y, w, h) with the origin at the BOTTOM left; ours are (x1, y1, x2, y2) from the top left."""
    x, y, w, h = rect
    return (round(x, 4), round(1.0 - (y + h), 4), round(x + w, 4), round(1.0 - y, 4))


def vision_available() -> bool:
    try:
        import Vision  # noqa: F401
    except ImportError:
        return False
    return True


class VisionDetails:
    MIN_LABEL_CONFIDENCE = 0.15

    def __init__(self) -> None:
        import objc
        import Vision
        from Foundation import NSData

        self._objc, self._vision, self._nsdata = objc, Vision, NSData

    # name -> Vision request class; each is optional because older macOS versions lack some of them
    REQUESTS = ("VNClassifyImageRequest", "VNRecognizeTextRequest", "VNRecognizeAnimalsRequest", "VNDetectHumanRectanglesRequest",
                "VNDetectBarcodesRequest", "VNGenerateAttentionBasedSaliencyImageRequest", "VNGenerateObjectnessBasedSaliencyImageRequest",
                "VNDetectFaceCaptureQualityRequest", "VNDetectFaceLandmarksRequest", "VNDetectDocumentSegmentationRequest",
                "VNDetectRectanglesRequest", "VNDetectHorizonRequest", "VNDetectHumanBodyPoseRequest", "VNDetectHumanHandPoseRequest",
                "VNCalculateImageAestheticsScoresRequest")

    def analyse(self, image_bytes: bytes) -> Details:
        vision = self._vision
        out = Details()
        with self._objc.autorelease_pool():
            data = self._nsdata.dataWithBytes_length_(image_bytes, len(image_bytes))
            handler = vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
            requests = {}
            for name in self.REQUESTS:
                cls = getattr(vision, name, None)
                if cls is not None:
                    try:
                        requests[name] = cls.alloc().init()
                    except Exception:
                        continue
            if "VNRecognizeTextRequest" in requests:
                requests["VNRecognizeTextRequest"].setRecognitionLevel_(vision.VNRequestTextRecognitionLevelAccurate)
            for name, request in requests.items():  # one request failing must not lose what the others found
                try:
                    ok, _error = handler.performRequests_error_([request], None)
                except Exception:
                    continue
                if ok:
                    try:
                        self._collect(name, request, out)
                    except Exception:
                        continue
        return out

    def _box(self, observation) -> tuple[float, float, float, float]:
        b = observation.boundingBox()
        return to_box((b.origin.x, b.origin.y, b.size.width, b.size.height))

    def _collect(self, name: str, request, out: Details) -> None:
        results = request.results() or []
        if name == "VNClassifyImageRequest":
            out.labels += [(str(r.identifier()), round(float(r.confidence()), 4)) for r in results if float(r.confidence()) >= self.MIN_LABEL_CONFIDENCE]
        elif name == "VNRecognizeTextRequest":
            for r in results:
                top = r.topCandidates_(1)
                if top:
                    out.texts.append((str(top[0].string()), round(float(top[0].confidence()), 4), self._box(r)))
        elif name == "VNRecognizeAnimalsRequest":
            for r in results:
                label = str(r.labels()[0].identifier()) if r.labels() else "animal"
                out.objects.append(("animal", label, round(float(r.confidence()), 4), self._box(r)))
        elif name == "VNDetectHumanRectanglesRequest":
            out.objects += [("person", "person", round(float(r.confidence()), 4), self._box(r)) for r in results]
        elif name == "VNDetectBarcodesRequest":
            out.objects += [("barcode", str(r.payloadStringValue() or r.symbology()), round(float(r.confidence()), 4), self._box(r)) for r in results]
        elif name in ("VNGenerateAttentionBasedSaliencyImageRequest", "VNGenerateObjectnessBasedSaliencyImageRequest"):
            kind = "attention" if "Attention" in name else "objectness"
            for r in results:
                for b in (r.salientObjects() or []):
                    box = b.boundingBox()
                    out.objects.append((kind, kind, round(float(b.confidence()), 4), to_box((box.origin.x, box.origin.y, box.size.width, box.size.height))))
        elif name == "VNDetectFaceCaptureQualityRequest":
            for r in results:
                quality = r.faceCaptureQuality()
                out.objects.append(("face", "face", round(float(quality), 4) if quality is not None else 0.0, self._box(r)))
        elif name == "VNDetectFaceLandmarksRequest":
            for r in results:  # head pose in degrees: yaw (turned left/right), roll (tilted); landmark count shows how much is visible
                landmarks = r.landmarks()
                count = len(landmarks.allPoints().normalizedPoints()) if landmarks is not None and landmarks.allPoints() is not None else 0
                yaw = float(r.yaw() or 0.0) * 57.2958 if hasattr(r, "yaw") and r.yaw() is not None else 0.0
                out.objects.append(("face_pose", f"yaw {yaw:.0f} landmarks {count}", round(yaw, 2), self._box(r)))
        elif name == "VNDetectDocumentSegmentationRequest":
            out.objects += [("document", "document", round(float(r.confidence()), 4), self._box(r)) for r in results]
        elif name == "VNDetectRectanglesRequest":
            out.objects += [("rectangle", "rectangle", round(float(r.confidence()), 4), self._box(r)) for r in results]
        elif name == "VNDetectHorizonRequest":
            for r in results:
                out.objects.append(("horizon", "horizon", round(float(r.angle()) * 57.2958, 2), (0.0, 0.0, 1.0, 1.0)))
        elif name in ("VNDetectHumanBodyPoseRequest", "VNDetectHumanHandPoseRequest"):
            kind = "body" if "Body" in name else "hand"
            out.objects += [(kind, kind, round(float(r.confidence()), 4), (0.0, 0.0, 1.0, 1.0)) for r in results]
        elif name == "VNCalculateImageAestheticsScoresRequest":
            for r in results:
                out.objects.append(("aesthetic", "aesthetic", round(float(r.overallScore()), 4), (0.0, 0.0, 1.0, 1.0)))
                if r.isUtility():
                    out.objects.append(("aesthetic", "utility", 1.0, (0.0, 0.0, 1.0, 1.0)))
