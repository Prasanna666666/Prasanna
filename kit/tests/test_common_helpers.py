from kit.groups import Groups
from kit.text import clean, day, json_object, squash


def test_groups_join_and_find():
    g = Groups([1, 2, 3, 4])
    g.join(1, 2)
    g.join(3, 4)
    assert g.same(1, 2) and g.same(3, 4) and not g.same(1, 3)
    g.join(2, 3)
    assert g.same(1, 4)


def test_text_helpers():
    assert squash(" a b\n c ") == "abc"
    assert clean("a\x00b\ud800c\n") == "abc\n"
    assert day("2026-03-04T10:00") is not None and day("nonsense") is None and day(None) is None
    assert json_object('{"a": 1}') == {"a": 1}
    assert json_object("") == {} and json_object("{bad") == {} and json_object("[1]") == {}
