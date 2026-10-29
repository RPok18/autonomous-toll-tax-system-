from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import vehicles as vehicle_api
from app.models.audit import AuditLog
from app.models.enums import PaymentStatus, VehicleClass
from app.models.transaction import Transaction
from app.models.vehicle import Vehicle
from app.schemas.vehicle import TollChargeRequest


class FakeQuery:
    def __init__(self, db, model):
        self.db = db
        self.model = model
        self.filters = {}

    def filter_by(self, **filters):
        self.filters.update(filters)
        return self

    def with_for_update(self):
        return self

    def first(self):
        if self.model is Vehicle:
            vehicle = self.db.vehicle
            if vehicle and vehicle.plate_number == self.filters.get("plate_number"):
                return vehicle
        else:
            plaza = self.db.plaza
            if plaza and all(getattr(plaza, key) == value for key, value in self.filters.items()):
                return plaza
        return None


class FakeSession:
    def __init__(self, vehicle=None, plaza=None):
        self.vehicle = vehicle
        self.plaza = plaza
        self.added = []
        self.commit_count = 0

    def query(self, model):
        return FakeQuery(self, model)

    def add(self, instance):
        self.added.append(instance)

    def flush(self):
        pass

    def commit(self):
        self.commit_count += 1

    def refresh(self, instance):
        pass


class FixedTollCalculator:
    amount = Decimal("65.00")

    def __init__(self, db):
        self.db = db

    def calculate(self, trip, vehicle, *, lane_id, identification_method):
        now = datetime.now(timezone.utc)
        return Transaction(
            transaction_id=uuid.uuid4(),
            plaza_id=self.db.plaza.plaza_id,
            lane_id=lane_id,
            trip_id=None,
            vehicle_id=vehicle.vehicle_id,
            tariff_id=uuid.uuid4(),
            plate_number=vehicle.plate_number,
            plate_confidence=None,
            tag_id=None,
            tag_confidence=None,
            identification_method=identification_method,
            vehicle_class=vehicle.vehicle_class,
            base_amount=self.amount,
            discount_amount=Decimal("0.00"),
            surcharge_amount=Decimal("0.00"),
            amount_charged=self.amount,
            currency="INR",
            payment_status=PaymentStatus.PENDING,
            applied_rules=[{"rule": "base_tariff"}],
            is_exception=False,
            latency_ms=None,
            transaction_time=now,
            created_at=now,
        )


class MissingTariffCalculator:
    def __init__(self, db):
        self.db = db

    def calculate(self, *args, **kwargs):
        raise vehicle_api.TariffNotFoundError("missing tariff")


def make_session(balance: str = "100.00") -> FakeSession:
    vehicle = SimpleNamespace(
        vehicle_id=uuid.uuid4(),
        plate_number="MH12AB1234",
        vehicle_class=VehicleClass.CAR_JEEP_VAN,
        balance=Decimal(balance),
    )
    plaza = SimpleNamespace(plaza_id=uuid.uuid4(), plaza_code="PLZ-A", is_active=True)
    return FakeSession(vehicle=vehicle, plaza=plaza)


def test_vehicle_lookup_normalizes_plate_number():
    db = make_session()

    vehicle = vehicle_api.get_vehicle_by_plate("mh 12-ab 1234", db)

    assert vehicle is db.vehicle


def test_toll_charge_creates_transaction_and_debits_balance(monkeypatch):
    db = make_session()
    monkeypatch.setattr(vehicle_api, "TollCalculator", FixedTollCalculator)

    result = vehicle_api.charge_vehicle(
        TollChargeRequest(plate_number="mh12ab1234", plaza_code="plz-a"),
        db,
        {"username": "operator"},
    )

    transactions = [item for item in db.added if isinstance(item, Transaction)]
    assert len(transactions) == 1
    assert transactions[0].payment_status == PaymentStatus.PAID
    assert db.vehicle.balance == Decimal("35.00")
    assert result.balance_after == Decimal("35.00")
    assert result.transaction.amount_charged == Decimal("65.00")
    assert db.commit_count == 1
    (audit_entry,) = [item for item in db.added if isinstance(item, AuditLog)]
    assert audit_entry.actor == "operator"
    assert audit_entry.action == "charge_vehicle_toll"
    assert audit_entry.metadata_json["plate_number"] == "MH12AB1234"
    assert audit_entry.metadata_json["amount_charged"] == "65.00"
    assert audit_entry.created_at.tzinfo is not None


def test_unknown_plate_returns_404_without_creating_transaction(monkeypatch):
    db = make_session()
    db.vehicle = None
    monkeypatch.setattr(vehicle_api, "TollCalculator", FixedTollCalculator)

    with pytest.raises(HTTPException) as exc_info:
        vehicle_api.charge_vehicle(
            TollChargeRequest(plate_number="XX00XX0000", plaza_code="PLZ-A"),
            db,
            {"username": "operator"},
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Vehicle not found"
    assert not any(isinstance(item, Transaction) for item in db.added)
    assert db.commit_count == 1
    (audit_entry,) = [item for item in db.added if isinstance(item, AuditLog)]
    assert audit_entry.actor == "operator"
    assert audit_entry.action == "charge_vehicle_toll_failed"
    assert audit_entry.metadata_json == {
        "plate_number": "XX00XX0000",
        "plaza_code": "PLZ-A",
        "amount_charged": None,
        "reason": "Vehicle not found",
    }
    assert audit_entry.created_at.tzinfo is not None


def test_unknown_plaza_is_audited(monkeypatch):
    db = make_session()
    db.plaza = None
    monkeypatch.setattr(vehicle_api, "TollCalculator", FixedTollCalculator)

    with pytest.raises(HTTPException) as exc_info:
        vehicle_api.charge_vehicle(
            TollChargeRequest(plate_number="MH12AB1234", plaza_code="PLZ-MISSING"),
            db,
            {"username": "operator"},
        )

    assert exc_info.value.status_code == 404
    (audit_entry,) = [item for item in db.added if isinstance(item, AuditLog)]
    assert audit_entry.metadata_json["reason"] == "Toll plaza not found"
    assert audit_entry.metadata_json["plaza_code"] == "PLZ-MISSING"
    assert db.commit_count == 1


def test_missing_tariff_is_audited(monkeypatch):
    db = make_session()
    monkeypatch.setattr(vehicle_api, "TollCalculator", MissingTariffCalculator)

    with pytest.raises(HTTPException) as exc_info:
        vehicle_api.charge_vehicle(
            TollChargeRequest(plate_number="MH12AB1234", plaza_code="PLZ-A"),
            db,
            {"username": "operator"},
        )

    assert exc_info.value.status_code == 404
    (audit_entry,) = [item for item in db.added if isinstance(item, AuditLog)]
    assert audit_entry.metadata_json["reason"] == "No applicable tariff found"
    assert db.commit_count == 1


def test_insufficient_balance_returns_402_without_debit_or_transaction(monkeypatch):
    db = make_session(balance="64.99")
    monkeypatch.setattr(vehicle_api, "TollCalculator", FixedTollCalculator)

    with pytest.raises(HTTPException) as exc_info:
        vehicle_api.charge_vehicle(
            TollChargeRequest(plate_number="MH12AB1234", plaza_code="PLZ-A"),
            db,
            {"username": "operator"},
        )

    assert exc_info.value.status_code == 402
    assert exc_info.value.detail == "Insufficient balance"
    assert db.vehicle.balance == Decimal("64.99")
    assert not any(isinstance(item, Transaction) for item in db.added)
    assert db.commit_count == 1
    (audit_entry,) = [item for item in db.added if isinstance(item, AuditLog)]
    assert audit_entry.actor == "operator"
    assert audit_entry.action == "charge_vehicle_toll_failed"
    assert audit_entry.metadata_json == {
        "plate_number": "MH12AB1234",
        "plaza_code": "PLZ-A",
        "amount_charged": "65.00",
        "reason": "Insufficient balance",
    }
    assert audit_entry.created_at.tzinfo is not None
