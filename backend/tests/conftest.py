from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.security import create_access_token  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app.models.enums import TollingType, UserRole  # noqa: E402
from app.models.highway import Highway  # noqa: E402
from app.models.plaza import Plaza  # noqa: E402
from app.models.user import User  # noqa: E402
from main import app  # noqa: E402
import app.models  # noqa: E402,F401


@pytest.fixture(scope="session")
def db_engine():
    if not TEST_DATABASE_URL:
        pytest.skip("Set TEST_DATABASE_URL to an isolated PostgreSQL test database")

    from sqlalchemy.engine import make_url

    test_url = make_url(TEST_DATABASE_URL)
    if test_url.get_backend_name() != "postgresql":
        pytest.fail("TEST_DATABASE_URL must use PostgreSQL")
    database_name = test_url.database or ""
    if "test" not in database_name.lower():
        pytest.fail("TEST_DATABASE_URL must point to a database whose name contains 'test'")

    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def seed(db):
    highway = Highway(
        nh_number="NH-TEST",
        name="Test Highway",
        states=["MH"],
        tolling_type=TollingType.OPEN,
    )
    db.add(highway)
    db.flush()
    plaza = Plaza(
        highway_id=highway.highway_id,
        plaza_code="PLZ-TEST",
        name="Test Plaza",
        state_code="MH",
        num_lanes=2,
    )
    db.add(plaza)
    db.commit()
    return SimpleNamespace(highway=highway, plaza=plaza)


@pytest.fixture()
def auth(db):
    users: dict[str, User] = {}
    for role in UserRole:
        user = User(
            username=role.value,
            hashed_password="test-only",
            role=role,
            is_active=True,
        )
        db.add(user)
        users[role.value] = user
    db.commit()
    for user in users.values():
        db.refresh(user)

    def headers(role: str) -> dict[str, str]:
        token = create_access_token(subject=str(users[role].user_id), role=role)
        return {"Authorization": f"Bearer {token}"}

    return headers


@pytest.fixture()
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
