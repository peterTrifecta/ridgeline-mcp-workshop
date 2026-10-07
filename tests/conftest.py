"""Tests run on their own copy of the databases, on a fixed date.

The environment has to be set before pricing_service is imported, because it
resolves its database paths at import time. conftest is imported first, so this
is the place for it. Test modules read the directory through the `data_dir`
fixture — importing it from here would create a second copy of this module.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="ridgeline-tests-"))
os.environ["RIDGELINE_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ["AS_OF"] = "2026-10-07"

import pytest  # noqa: E402

from data import generate  # noqa: E402


@pytest.fixture(scope="session")
def as_of():
    return generate.as_of_date()


@pytest.fixture(scope="session")
def data_dir(as_of):
    generate.build(_TEST_DATA_DIR / "crm.db", _TEST_DATA_DIR / "erp.db", as_of)
    return _TEST_DATA_DIR


@pytest.fixture(scope="session")
def crm(data_dir):
    con = sqlite3.connect(data_dir / "crm.db")
    con.row_factory = sqlite3.Row
    yield con
    con.close()


@pytest.fixture(scope="session")
def erp(data_dir):
    con = sqlite3.connect(data_dir / "erp.db")
    con.row_factory = sqlite3.Row
    yield con
    con.close()


@pytest.fixture(scope="session")
def service(data_dir):
    """pricing_service, pointed at the test databases."""
    import pricing_service
    assert pricing_service.CRM_DB == data_dir / "crm.db"
    return pricing_service
