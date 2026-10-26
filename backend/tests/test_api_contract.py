from __future__ import annotations

import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import vehicles as vehicle_api
from app.core.rbac import get_current_identity
from app.database import get_db
from app.models.device import Device
from app.models.enums import (
    DeviceStatus,
    DeviceType,
    ExceptionType,
    IdentificationMethod,
    PaymentStatus,
    UserRole,
    VehicleClass,
)
from app.models.exception import ExceptionRecord
from app.models.plaza import Plaza
from app.models.transaction import Transaction
from app.models.user import User
from app.models.vehicle import Vehicle
from app.schemas.vehicle import TollChargeResponse
from main import app


VEHICLE_ID = uuid.UUID("00000000-0000-0000-0000-000000000101")
TRANSACTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000201")
DEVICE_ID = uuid.UUID("00000000-0000-0000-0000-000000000301")
EXCEPTION_ID = uuid.UUID("00000000-0000-0000-0000-000000000401")
PLAZA_ID = uuid.UUID("00000000-0000-0000-0000-000000000501")
MISSING_ID = uuid.UUID("00000000-0000-0000-0000-000000000999")


def apply_model_defaults(instance: Any) -> None:
    for attribute in inspect(instance).mapper.column_attrs:
        column = attribute.columns[0]
        if getattr(instance, attribute.key) is not None or column.default is None:
            continue
        default = column.default.arg
        if callable(default):
            try:
                value = default()
            except TypeError as exc:
                if "required positional argument: 'ctx'" not in str(exc):
                    raise
                value = default(None)
        else:
            value = default
        setattr(instance, attribute.key, value)


class FakeDatabase:
    def __init__(self) -> None:
        self.records: dict[type, list[Any]] = {}
        self.vehicle_lock = Lock()
        self.lock_requests = 0
        self.lock_request_guard = Lock()

    def add_seed(self, instance: Any) -> None:
        apply_model_defaults(instance)
        self.records.setdefault(type(instance), []).append(instance)

    def session(self) -> FakeSession:
        return FakeSession(self)


class FakeQuery:
    def __init__(self, session: FakeSession, model: type) -> None:
        self.session = session
        self.model = model
        self.filters: dict[str, Any] = {}
        self.lock_vehicle = False
        self.limit_value: int | None = None
        self.offset_value = 0

    def filter_by(self, **filters: Any) -> FakeQuery:
        self.filters.update(filters)
        return self

    def with_for_update(self) -> FakeQuery:
        self.lock_vehicle = self.model is Vehicle
        if self.lock_vehicle:
            with self.session.database.lock_request_guard:
                self.session.database.lock_requests += 1
        return self

    def order_by(self, *args: Any) -> FakeQuery:
        return self

    def filter(self, *args: Any) -> FakeQuery:
        return self

    def limit(self, value: int) -> FakeQuery:
        self.limit_value = value
        return self

    def offset(self, value: int) -> FakeQuery:
        self.offset_value = value
        return self

    def _matches(self, instance: Any) -> bool:
        return all(getattr(instance, name, None) == value for name, value in self.filters.items())

    def first(self) -> Any | None:
        if self.lock_vehicle:
            self.session.database.vehicle_lock.acquire()
            self.session.lock_held = True
        return next(
            (record for record in self.session.database.records.get(self.model, []) if self._matches(record)),
            None,
        )

    def all(self) -> list[Any]:
        records = [
            record for record in self.session.database.records.get(self.model, [])
            if self._matches(record)
        ]
        end = None if self.limit_value is None else self.offset_value + self.limit_value
        return records[self.offset_value:end]


class FakeSession:
    def __init__(self, database: FakeDatabase) -> None:
        self.database = database
        self.pending: list[Any] = []
        self.lock_held = False

    def query(self, model: type) -> FakeQuery:
        return FakeQuery(self, model)

    def add(self, instance: Any) -> None:
        self.pending.append(instance)

    def _persist_pending(self) -> None:
        for instance in self.pending:
            apply_model_defaults(instance)
            records = self.database.records.setdefault(type(instance), [])
            if instance not in records:
                records.append(instance)
        self.pending.clear()

    def flush(self) -> None:
        for instance in self.pending:
            apply_model_defaults(instance)

    def commit(self) -> None:
        self._persist_pending()
        self._release_lock()

    def refresh(self, instance: Any) -> None:
        apply_model_defaults(instance)

    def close(self) -> None:
        self._release_lock()

    def _release_lock(self) -> None:
        if self.lock_held:
            self.lock_held = False
            self.database.vehicle_lock.release()


class FixedTollCalculator:
    def __init__(self, db: FakeSession) -> None:
        self.db = db

    def calculate(
        self,
        trip: Any,
        vehicle: Vehicle,
        *,
        lane_id: str,
        identification_method: IdentificationMethod,
    ) -> Transaction:
        return Transaction(
            transaction_id=uuid.uuid4(),
            plaza_id=PLAZA_ID,
            lane_id=lane_id,
            vehicle_id=vehicle.vehicle_id,
            plate_number=vehicle.plate_number,
            identification_method=identification_method,
            vehicle_class=vehicle.vehicle_class,
            base_amount=Decimal("65.00"),
            discount_amount=Decimal("0.00"),
            surcharge_amount=Decimal("0.00"),
            amount_charged=Decimal("65.00"),
            currency="INR",
            payment_status=PaymentStatus.PENDING,
            applied_rules=[],
            is_exception=False,
            transaction_time=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch):
    database = FakeDatabase()
    vehicle = Vehicle(
        vehicle_id=VEHICLE_ID,
        plate_number="MH12AB1234",
        registration_state="MH",
        vehicle_class=VehicleClass.CAR_JEEP_VAN,
        balance=Decimal("100.00"),
        fastag_id="TAG-1234",
        fastag_issuer_bank="Test Bank",
        is_commercial=False,
        is_exempt=False,
        is_blacklisted=False,
    )
    transaction = Transaction(
        transaction_id=TRANSACTION_ID,
        plaza_id=PLAZA_ID,
        lane_id="L1",
        vehicle_id=VEHICLE_ID,
        plate_number="MH12AB1234",
        identification_method=IdentificationMethod.MANUAL,
        vehicle_class=VehicleClass.CAR_JEEP_VAN,
        base_amount=Decimal("65.00"),
        discount_amount=Decimal("0.00"),
        surcharge_amount=Decimal("0.00"),
        amount_charged=Decimal("65.00"),
        currency="INR",
        payment_status=PaymentStatus.PAID,
        applied_rules=[],
        is_exception=False,
    )
    device = Device(
        device_id=DEVICE_ID,
        name="Lane RFID",
        device_type=DeviceType.RFID_READER,
        plaza_id=PLAZA_ID,
        lane_id="L1",
        status=DeviceStatus.OFFLINE,
    )
    exception_record = ExceptionRecord(
        exception_id=EXCEPTION_ID,
        transaction_id=TRANSACTION_ID,
        plaza_id=PLAZA_ID,
        lane_id="L1",
        exception_type=ExceptionType.DEVICE_FAULT,
        details="Reader disconnected",
        resolved=False,
    )
    for record in (
        vehicle,
        transaction,
        device,
        exception_record,
        Plaza(plaza_id=PLAZA_ID, plaza_code="PLZ-A", is_active=True),
        User(
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000601"),
            username="operator",
            hashed_password="hashed",
            role=UserRole.ADMIN,
            is_active=True,
        ),
    ):
        database.add_seed(record)

    def get_fake_db():
        session = database.session()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = get_fake_db
    app.dependency_overrides[get_current_identity] = lambda: {
        "username": "operator",
        "role": UserRole.ADMIN.value,
    }
    monkeypatch.setattr(vehicle_api, "TollCalculator", FixedTollCalculator)
    monkeypatch.setattr("app.api.auth.verify_password", lambda plain, hashed: plain == "secret")

    client = TestClient(app)
    try:
        yield client, database
    finally:
        client.close()
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    ("method", "path", "payload", "params", "expected_status"),
    [
        ("POST", "/auth/login", {"username": "operator", "password": "secret"}, None, 200),
        ("POST", "/vehicles", {"plate_number": "mh 12-ab 9999", "balance": "100.00"}, None, 201),
        ("GET", f"/vehicles/{VEHICLE_ID}", None, None, 200),
        ("GET", "/vehicles/by-plate/mh%2012-ab%201234", None, None, 200),
        ("POST", "/vehicles/charge", {"plate_number": "mh12ab1234", "plaza_code": "plz-a"}, None, 201),
        ("GET", "/vehicles", None, {"limit": 10}, 200),
        (
            "POST",
            "/transactions",
            {"plaza_id": str(PLAZA_ID), "lane_id": "L2", "amount_charged": "15.00"},
            None,
            201,
        ),
        ("GET", f"/transactions/{TRANSACTION_ID}", None, None, 200),
        ("GET", f"/transactions/by-vehicle/{VEHICLE_ID}", None, None, 200),
        ("GET", "/transactions", None, {"plate_number": "mh12ab1234"}, 200),
        ("POST", "/devices", {"name": "New reader", "device_type": "rfid_reader"}, None, 201),
        ("GET", f"/devices/{DEVICE_ID}", None, None, 200),
        ("GET", "/devices", None, {"status_filter": "offline"}, 200),
        ("PATCH", f"/devices/{DEVICE_ID}/heartbeat", None, None, 200),
        ("POST", "/exceptions", {"exception_type": "device_fault"}, None, 201),
        ("GET", f"/exceptions/{EXCEPTION_ID}", None, None, 200),
        ("GET", "/exceptions", None, {"resolved": "false"}, 200),
        ("PATCH", f"/exceptions/{EXCEPTION_ID}/resolve", None, None, 200),
        ("GET", "/health", None, None, 200),
    ],
)
def test_every_api_endpoint_has_a_success_case(
    api_client,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    params: dict[str, Any] | None,
    expected_status: int,
):
    client, _ = api_client
    response = client.request(method, path, json=payload, params=params)

    assert response.status_code == expected_status, response.text


@pytest.mark.parametrize(
    ("method", "path", "payload", "params", "expected_status"),
    [
        ("POST", "/auth/login", {"username": "operator", "password": "wrong"}, None, 401),
        ("POST", "/vehicles", {"plate_number": "MH12AB9999", "balance": "-1"}, None, 422),
        ("GET", f"/vehicles/{MISSING_ID}", None, None, 404),
        ("GET", "/vehicles/by-plate/XX00XX0000", None, None, 404),
        (
            "POST",
            "/vehicles/charge",
            {"plate_number": "XX00XX0000", "plaza_code": "PLZ-A"},
            None,
            404,
        ),
        ("GET", "/vehicles", None, {"limit": "not-an-integer"}, 422),
        ("POST", "/transactions", {"lane_id": "L2"}, None, 422),
        ("GET", f"/transactions/{MISSING_ID}", None, None, 404),
        ("GET", "/transactions/by-vehicle/not-a-uuid", None, None, 422),
        ("GET", "/transactions", None, {"limit": 0}, 422),
        ("POST", "/devices", {"name": "Missing type"}, None, 422),
        ("GET", f"/devices/{MISSING_ID}", None, None, 404),
        ("GET", "/devices", None, {"status_filter": "unknown"}, 422),
        ("PATCH", f"/devices/{MISSING_ID}/heartbeat", None, None, 404),
        ("POST", "/exceptions", {"details": "Missing type"}, None, 422),
        ("GET", f"/exceptions/{MISSING_ID}", None, None, 404),
        ("GET", "/exceptions", None, {"resolved": "not-a-boolean"}, 422),
        ("PATCH", f"/exceptions/{MISSING_ID}/resolve", None, None, 404),
        ("POST", "/health", None, None, 405),
    ],
)
def test_every_api_endpoint_has_an_error_case(
    api_client,
    method: str,
    path: str,
    payload: dict[str, Any] | None,
    params: dict[str, Any] | None,
    expected_status: int,
):
    client, _ = api_client
    response = client.request(method, path, json=payload, params=params)

    assert response.status_code == expected_status, response.text


def test_two_simultaneous_charges_do_not_overdraw_balance(api_client):
    client, database = api_client
    vehicle = database.records[Vehicle][0]
    vehicle.balance = Decimal("65.00")
    request_body = {"plate_number": "MH12AB1234", "plaza_code": "PLZ-A"}

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: client.post("/vehicles/charge", json=request_body),
                range(2),
            )
        )

    assert sorted(response.status_code for response in responses) == [201, 402]
    assert database.lock_requests == 2
    assert vehicle.balance == Decimal("0.00")
    assert vehicle.balance >= Decimal("0.00")
    successful_charge = next(response for response in responses if response.status_code == 201)
    assert TollChargeResponse.model_validate(successful_charge.json()).balance_after == Decimal("0.00")
