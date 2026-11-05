"""Text recognition: Apple's Vision framework on a Mac, or Tesseract where there is no Vision (the Docker image).

Both run locally and send nothing anywhere. Vision needs no model download; Tesseract is installed with the image.
"""

from __future__ import annotations

import shutil
import subprocess


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


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def text_available() -> bool:
    """True when some local text reader exists: Apple Vision, or Tesseract."""
    return vision_available() or tesseract_available()


class TesseractOCR:
    """:class:`~aperture.ml.protocols.TextRecognizer` backed by the ``tesseract`` program (reads the picture from stdin, no files, no network)."""

    def __init__(self, languages: str = "eng+nld") -> None:
        self._languages = languages

    def read(self, image_bytes: bytes) -> str:
        try:
            done = subprocess.run(
                ["tesseract", "stdin", "stdout", "-l", self._languages],
                input=image_bytes,
                capture_output=True,
                timeout=60,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return ""
        if done.returncode != 0 and self._languages != "eng":  # a language pack is missing: fall back to English
            return TesseractOCR("eng").read(image_bytes)
        return done.stdout.decode("utf-8", "replace").strip() if done.returncode == 0 else ""
