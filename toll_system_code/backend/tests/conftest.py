"""Shared fixtures for the API tests that run against a real PostgreSQL database.

Safety rules:
* The tests wipe every table, so they only ever run against a database whose
  name ends in ``_test``. By default that is the development database name plus
  ``_test`` (``toll_system`` -> ``toll_system_test``), on the same server and
  with the same credentials as ``DATABASE_URL``. Set ``TEST_DATABASE_URL`` to
  use something else; a name that does not end in ``_test`` is refused.
* The database is created if it does not exist, rebuilt from the Alembic
  migrations at the start of a run, and emptied before every test.
* When no PostgreSQL server can be reached the API tests are skipped, not failed.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Test-only passwords for the four seeded users (one per role).
PASSWORDS = {role: f"{role}-test-pass" for role in ("admin", "operator", "auditor", "viewer")}
CAR_FARE = Decimal("65.00")
PLAZA_CODE = "PLZ-T1"


def _test_database_url():
    from sqlalchemy.engine import make_url

    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        url = make_url(explicit)
    else:
        from app.config import get_settings

        base = make_url(get_settings().database_url)
        url = base.set(database=f"{base.database}_test")
    if not (url.database or "").endswith("_test"):
        pytest.exit(
            f"Refusing to run: test database name {url.database!r} must end with '_test' "
            "because the tests delete all rows.",
            returncode=2,
        )
    return url


def _ensure_database(url) -> None:
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    probe = create_engine(url)
    try:
        with probe.connect():
            return
    except OperationalError:
        pass
    finally:
        probe.dispose()

    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{url.database}" ENCODING \'UTF8\' TEMPLATE template0'))
    finally:
        admin.dispose()


@pytest.fixture(scope="session")
def db_engine():
    from sqlalchemy import create_engine, text

    url = _test_database_url()
    try:
        _ensure_database(url)
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
    except Exception as exc:  # no server, wrong credentials, no permission
        pytest.skip(f"PostgreSQL test database is not available ({type(exc).__name__})")

    env = {**os.environ, "DATABASE_URL": url.render_as_string(hide_password=False)}
    result = subprocess.run(
        [sys.executable, "-c", "from alembic.config import main; main(argv=['upgrade', 'head'])"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"alembic upgrade head failed on the empty test database:\n{result.stderr[-2000:]}")

    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def session_factory(db_engine):
    from sqlalchemy.orm import sessionmaker

    factory = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)

    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.user import User

    with factory() as session:
        for role in UserRole:
            session.add(
                User(username=role.value, hashed_password=hash_password(PASSWORDS[role.value]), role=role)
            )
        session.commit()
    return factory


@pytest.fixture()
def db(session_factory, db_engine):
    """A session for arranging and checking data; every table except users is emptied first."""
    from sqlalchemy import text

    from app.database import Base

    tables = [t.name for t in Base.metadata.sorted_tables if t.name != "users"]
    with db_engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(tables) + " RESTART IDENTITY CASCADE"))

    session = session_factory()
    yield session
    session.close()


@pytest.fixture()
def seed(db):
    """One open-tolling plaza with a car tariff of 65.00 (no discounts, no surcharge)."""
    from types import SimpleNamespace

    from app.models.enums import TollingType, VehicleClass
    from app.models.highway import Highway
    from app.models.plaza import Plaza
    from app.models.tariff import Tariff

    highway = Highway(nh_number="NH-T", name="Test highway", states=["MH"], tolling_type=TollingType.OPEN)
    db.add(highway)
    db.flush()
    plaza = Plaza(highway_id=highway.highway_id, plaza_code=PLAZA_CODE, name="Test plaza", state_code="MH")
    db.add(plaza)
    db.flush()
    tariff = Tariff(
        plaza_id=plaza.plaza_id,
        vehicle_class=VehicleClass.CAR_JEEP_VAN,
        base_fare=CAR_FARE,
        effective_from=date(2020, 1, 1),
    )
    db.add(tariff)
    db.commit()
    return SimpleNamespace(highway=highway, plaza=plaza, tariff=tariff, plaza_code=PLAZA_CODE, fare=CAR_FARE)


@pytest.fixture()
def app_with_db(session_factory):
    from app.database import get_db
    from main import app

    def _override():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override
    yield app
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def client(app_with_db):
    from fastapi.testclient import TestClient

    # raise_server_exceptions=False: an unhandled error becomes a 500 response the test can assert on.
    return TestClient(app_with_db, raise_server_exceptions=False)


@pytest.fixture(scope="session")
def _tokens():
    return {}


@pytest.fixture()
def auth(client, _tokens):
    """auth("operator") -> Authorization header for that seeded user (logs in once per run)."""

    def _headers(role: str) -> dict:
        if role not in _tokens:
            response = client.post("/auth/login", json={"username": role, "password": PASSWORDS[role]})
            assert response.status_code == 200, response.text
            _tokens[role] = response.json()["access_token"]
        return {"Authorization": f"Bearer {_tokens[role]}"}

    return _headers
