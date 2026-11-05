"""Reading Apple Vision results. The real framework only exists on a Mac, so stand-in result objects are used."""

from types import SimpleNamespace

from images.ml.vision_details import Details, VisionDetails


class Fake:
    def __init__(self, **values):
        self._v = values

    def __getattr__(self, name):
        if name.startswith("_") or name not in self._v:
            raise AttributeError(name)
        value = self._v[name]
        return lambda *args: value


def _result(**values):
    values["boundingBox"] = SimpleNamespace(
        origin=SimpleNamespace(x=0.1, y=0.2), size=SimpleNamespace(width=0.3, height=0.4)
    )  # a plain struct, like CGRect
    return Fake(**values)


class _Request:
    def __init__(self, results):
        self._results = results

    def results(self):
        return self._results


def _collect(name, results):
    out = Details()
    object.__new__(VisionDetails)._collect(name, _Request(results), out)
    return out


def test_labels_below_the_confidence_floor_are_dropped():
    out = _collect(
        "VNClassifyImageRequest", [_result(identifier="cat", confidence=0.9), _result(identifier="x", confidence=0.001)]
    )
    assert [name for name, _ in out.labels] == ["cat"]


def test_text_without_a_candidate_is_skipped():
    out = _collect(
        "VNRecognizeTextRequest", [_result(topCandidates_=[Fake(string="hello", confidence=0.8)]), _result(topCandidates_=[])]
    )
    assert [t[0] for t in out.texts] == ["hello"]


def test_people_documents_and_pose_are_recorded_by_kind():
    assert [o[0] for o in _collect("VNDetectHumanRectanglesRequest", [_result(confidence=0.6)]).objects] == ["person"]
    assert [o[0] for o in _collect("VNDetectDocumentSegmentationRequest", [_result(confidence=0.4)]).objects] == ["document"]
    assert [o[0] for o in _collect("VNDetectHumanHandPoseRequest", [_result(confidence=0.2)]).objects] == ["hand"]
    assert [o[0] for o in _collect("VNDetectHumanBodyPoseRequest", [_result(confidence=0.2)]).objects] == ["body"]


def test_an_unknown_request_adds_nothing():
    out = _collect("VNSomethingNew", [_result(confidence=1)])
    assert not out.objects and not out.labels and not out.texts
