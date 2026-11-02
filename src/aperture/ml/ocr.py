"""Text recognition with Apple's Vision framework (via PyObjC).

Runs locally on the Neural Engine, needs no model download and handles dozens
of languages automatically.  Only available on macOS.
"""

from __future__ import annotations


def vision_available() -> bool:
    try:
        import Vision  # noqa: F401
    except ImportError:
        return False
    return True


class VisionOCR:
    """:class:`~aperture.ml.protocols.TextRecognizer` backed by Vision."""

    def __init__(self) -> None:
        import objc
        import Vision
        from Foundation import NSData

        self._objc, self._vision, self._nsdata = objc, Vision, NSData

    def read(self, image_bytes: bytes) -> str:
        vision = self._vision
        with self._objc.autorelease_pool():
            data = self._nsdata.dataWithBytes_length_(image_bytes, len(image_bytes))
            handler = vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
            request = vision.VNRecognizeTextRequest.alloc().init()
            request.setRecognitionLevel_(vision.VNRequestTextRecognitionLevelAccurate)
            request.setUsesLanguageCorrection_(True)
            if hasattr(request, "setAutomaticallyDetectsLanguage_"):  # macOS 13+
                request.setAutomaticallyDetectsLanguage_(True)
            ok, _error = handler.performRequests_error_([request], None)
            if not ok:
                return ""
            lines: list[str] = []
            for observation in request.results() or []:
                candidates = observation.topCandidates_(1)
                if candidates:
                    lines.append(str(candidates[0].string()))
            return "\n".join(lines)
