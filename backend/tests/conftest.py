# Shared pytest fixtures. Only the tenancy tests (test_tenancy.py) need a
# database -- everything else in this suite is deliberately DB-free (see
# each test file's own comment) -- so this is the one place a session
# gets set up.
#
# SQLite in-memory rather than a real Postgres: fast, needs no running
# service, and every query these tests exercise (db.get, db.query(...)
# .filter_by(...)) is plain SQLAlchemy ORM -- none of it depends on a
# Postgres-only feature. The app's raw-SQL scripts (backend/scripts/) and
# Postgres-specific migrations aren't covered by this fixture and
# shouldn't be tested through it.

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base

# Importing app.models (not used directly below) registers every central
# model on Base.metadata -- without this import, create_all() would
# create no tables at all, since nothing else here references the model
# classes.
import app.models  # noqa: F401


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
