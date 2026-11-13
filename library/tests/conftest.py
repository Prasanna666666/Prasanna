import pytest
from kit import db

from library import store


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "library.db")
    db.migrate(c, [store.MODULE])
    return c


@pytest.fixture(autouse=True)
def _fresh_status_cache():
    """The status numbers are reused for a few seconds; every test starts without them."""
    from library import web

    web._CACHE.clear()
    yield


@pytest.fixture(autouse=True)
def _health_lock_on(request, monkeypatch):
    """Health is open by default; the tests of the optional lock switch it on."""
    if "open_health" not in request.keywords:
        monkeypatch.setattr(store, "HEALTH_LOCK", True)
