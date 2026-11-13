from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

from app.models.enums import ExceptionType, IdentificationMethod, PaymentStatus, VehicleClass
from app.models.exception import ExceptionRecord
from app.models.plaza import Plaza
from app.models.transaction import Transaction
from app.simulation.persistence import persist_simulation_passes
from app.simulation.runner import PassRecord


class FakeQuery:
    def __init__(self, entity, rows):
        self.entity = entity
        self.rows = rows
        self.ids = []

    def filter_by(self, **_):
        return self

    def filter(self, *criteria):
        if self.entity is Transaction.transaction_id:
            self.ids = criteria[0].right.value
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        if self.entity is Transaction.transaction_id:
            return [(row.transaction_id,) for row in self.rows if row.transaction_id in self.ids]
        return self.rows


class FakeSession:
    def __init__(self, plaza):
        self.plaza = plaza
        self.rows = []

    def query(self, entity):
        if entity is Plaza:
            return FakeQuery(entity, [self.plaza])
        if entity is Transaction.transaction_id:
            return FakeQuery(entity, [row for row in self.rows if isinstance(row, Transaction)])
        return FakeQuery(entity, [])

    def add_all(self, rows):
        self.rows.extend(rows)

    def commit(self):
        pass


def test_persist_simulation_passes_is_idempotent_without_a_database():
    plaza = SimpleNamespace(plaza_id=uuid.uuid4(), num_lanes=4)
    db = FakeSession(plaza)
    record = PassRecord(
        pass_no=0,
        vehicle_class=VehicleClass.CAR_JEEP_VAN.value,
        hour=17,
        anpr_plate="MH12AB1234",
        anpr_confidence=0.93,
        method=IdentificationMethod.ANPR_ONLY.value,
        resolved_plate="MH12AB1234",
        charge_status="paid",
        expected_amount=65.0,
        charged_amount=65.0,
    )

    assert persist_simulation_passes(
        db, [record], plaza_code="PLZ-TEST", scenario="S0", seed=42
    ) == 1
    assert persist_simulation_passes(
        db, [record], plaza_code="PLZ-TEST", scenario="S0", seed=42
    ) == 0
    assert len(db.rows) == 1
    assert db.rows[0].is_exception is False
    assert "simulation_demo" in db.rows[0].applied_rules


def test_persist_simulation_passes_adds_dashboard_records_once(db, seed):
    records = [
        PassRecord(
            pass_no=0,
            vehicle_class=VehicleClass.CAR_JEEP_VAN.value,
            hour=17,
            anpr_plate="MH12AB1234",
            anpr_confidence=0.93,
            rfid_tag="TAG-MH12AB1234",
            rfid_confidence=0.88,
            rfid_latency_ms=45.2,
            method=IdentificationMethod.ANPR_ONLY.value,
            resolved_plate="MH12AB1234",
            charge_status="paid",
            expected_amount=65.0,
            charged_amount=65.0,
        ),
        PassRecord(
            pass_no=1,
            vehicle_class=VehicleClass.CAR_JEEP_VAN.value,
            hour=18,
            method=IdentificationMethod.UNRESOLVED.value,
            fusion_exception=True,
            notes="no_usable_signal",
            charge_status="unresolved",
            expected_amount=65.0,
        ),
    ]

    assert persist_simulation_passes(
        db, records, plaza_code=seed.plaza.plaza_code, scenario="S10", seed=42
    ) == 2
    assert persist_simulation_passes(
        db, records, plaza_code=seed.plaza.plaza_code, scenario="S10", seed=42
    ) == 0

    transactions = db.query(Transaction).order_by(Transaction.lane_id).all()
    assert len(transactions) == 2
    paid = next(row for row in transactions if row.payment_status == PaymentStatus.PAID)
    held = next(row for row in transactions if row.payment_status == PaymentStatus.PENDING)
    assert paid.plaza_id == seed.plaza.plaza_id
    assert paid.plate_number == "MH12AB1234"
    assert paid.amount_charged == Decimal("65.00")
    assert paid.lane_id.startswith("SIM-S10-")
    assert "simulation_demo" in paid.applied_rules
    assert held.is_exception

    exceptions = db.query(ExceptionRecord).all()
    assert len(exceptions) == 1
    assert exceptions[0].transaction_id == held.transaction_id
    assert exceptions[0].exception_type == ExceptionType.NO_IDENTIFICATION
