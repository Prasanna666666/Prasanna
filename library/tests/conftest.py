import pytest
from kit import db

from library import store


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "library.db")
    db.migrate(c, [store.MODULE])
    return c
