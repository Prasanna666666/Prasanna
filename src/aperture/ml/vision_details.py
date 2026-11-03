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

    def analyse(self, image_bytes: bytes) -> Details:
        vision = self._vision
        out = Details()
        with self._objc.autorelease_pool():
            data = self._nsdata.dataWithBytes_length_(image_bytes, len(image_bytes))
            handler = vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
            requests = {
                "labels": vision.VNClassifyImageRequest.alloc().init(),
                "text": vision.VNRecognizeTextRequest.alloc().init(),
                "animals": vision.VNRecognizeAnimalsRequest.alloc().init(),
                "humans": vision.VNDetectHumanRectanglesRequest.alloc().init(),
                "barcodes": vision.VNDetectBarcodesRequest.alloc().init(),
                "attention": vision.VNGenerateAttentionBasedSaliencyImageRequest.alloc().init(),
            }
            requests["text"].setRecognitionLevel_(vision.VNRequestTextRecognitionLevelAccurate)
            ok, _error = handler.performRequests_error_(list(requests.values()), None)
            if not ok:
                return out
            for r in requests["labels"].results() or []:
                if float(r.confidence()) >= self.MIN_LABEL_CONFIDENCE:
                    out.labels.append((str(r.identifier()), round(float(r.confidence()), 4)))
            for r in requests["text"].results() or []:
                top = r.topCandidates_(1)
                if top:
                    b = r.boundingBox()
                    out.texts.append((str(top[0].string()), round(float(top[0].confidence()), 4),
                                      to_box((b.origin.x, b.origin.y, b.size.width, b.size.height))))
            for kind, key in (("animal", "animals"), ("person", "humans"), ("barcode", "barcodes")):
                for r in requests[key].results() or []:
                    b = r.boundingBox()
                    label = kind
                    if kind == "animal" and r.labels():
                        label = str(r.labels()[0].identifier())
                    if kind == "barcode":
                        label = str(r.payloadStringValue() or r.symbology())
                    out.objects.append((kind, label, round(float(r.confidence()), 4),
                                        to_box((b.origin.x, b.origin.y, b.size.width, b.size.height))))
            for r in requests["attention"].results() or []:
                for b in (r.salientObjects() or []):
                    box = b.boundingBox()
                    out.objects.append(("salient", "salient", round(float(b.confidence()), 4),
                                        to_box((box.origin.x, box.origin.y, box.size.width, box.size.height))))
        return out
