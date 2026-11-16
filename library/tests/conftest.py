import pytest
from kit import db

from library import scanstatus, store


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "library.db")
    db.migrate(c, [store.MODULE])
    return c


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    """The status numbers are reused for a few seconds; every test starts without them."""

    scanstatus._CACHE.clear()
    yield
