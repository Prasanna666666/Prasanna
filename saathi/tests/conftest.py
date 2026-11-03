import pytest

from saathi import db
from saathi.modules import ALL


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    db.migrate(c, ALL)
    return c
