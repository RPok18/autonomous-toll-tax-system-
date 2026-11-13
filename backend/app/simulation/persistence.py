"""Opt-in persistence of simulated passes for dashboard demonstrations."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.enums import (
    ExceptionType,
    IdentificationMethod,
    PaymentStatus,
    VehicleClass,
)
from app.models.exception import ExceptionRecord
from app.models.plaza import Plaza
from app.models.transaction import Transaction
from app.simulation.runner import PassRecord

_DEMO_NAMESPACE = uuid.UUID("838489ef-6474-4cdd-a015-9f2ee29fa709")
_SIMULATION_START = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _transaction_id(plaza_id: uuid.UUID, scenario: str, seed: int, pass_no: int) -> uuid.UUID:
    return uuid.uuid5(_DEMO_NAMESPACE, f"{plaza_id}:{scenario}:{seed}:{pass_no}")


def _exception_type(record: PassRecord) -> ExceptionType:
    if "anpr_rfid_conflict" in record.notes:
        return ExceptionType.TAG_MISMATCH
    if record.charge_status == "no_vehicle":
        return ExceptionType.TAG_NOT_FOUND
    if record.charge_status == "insufficient_balance":
        return ExceptionType.POLICY_VIOLATION
    if record.resolved_plate is None:
        return ExceptionType.NO_IDENTIFICATION
    return ExceptionType.LOW_CONFIDENCE_PLATE


def persist_simulation_passes(
    db: Session,
    records: list[PassRecord],
    *,
    plaza_code: str,
    scenario: str,
    seed: int,
) -> int:
    """Persist one deterministic transaction per simulated pass; repeated imports are skipped."""
    plaza = db.query(Plaza).filter_by(plaza_code=plaza_code, is_active=True).first()
    if plaza is None:
        raise ValueError(f"Active plaza {plaza_code!r} was not found; seed the database first.")
    if not records:
        return 0

    transaction_ids = [
        _transaction_id(plaza.plaza_id, scenario, seed, record.pass_no)
        for record in records
    ]
    existing_ids = {
        row[0]
        for row in db.query(Transaction.transaction_id)
        .filter(Transaction.transaction_id.in_(transaction_ids))
        .all()
    }

    transactions: list[Transaction] = []
    exceptions: list[ExceptionRecord] = []
    for record, transaction_id in zip(records, transaction_ids):
        if transaction_id in existing_ids:
            continue

        vehicle_class = VehicleClass(record.vehicle_class)
        is_exception = (
            record.fusion_exception
            or record.charge_status in {"no_vehicle", "insufficient_balance"}
        )
        transaction = Transaction(
            transaction_id=transaction_id,
            plaza_id=plaza.plaza_id,
            lane_id=f"SIM-{scenario}-L{record.pass_no % max(plaza.num_lanes, 1) + 1}",
            plate_number=record.resolved_plate,
            plate_confidence=Decimal(str(record.anpr_confidence)) if record.anpr_plate else None,
            tag_id=record.rfid_tag,
            tag_confidence=Decimal(str(record.rfid_confidence)) if record.rfid_tag else None,
            identification_method=IdentificationMethod(record.method),
            vehicle_class=vehicle_class,
            base_amount=Decimal(str(record.expected_amount)),
            amount_charged=Decimal(str(record.charged_amount)),
            currency="INR",
            payment_status=(
                PaymentStatus.PAID if record.charge_status == "paid"
                else PaymentStatus.FAILED if record.charge_status == "insufficient_balance"
                else PaymentStatus.PENDING
            ),
            applied_rules=[
                "simulation_demo",
                {"scenario": scenario, "seed": seed, "pass_no": record.pass_no},
                *([record.notes] if record.notes else []),
            ],
            is_exception=is_exception,
            latency_ms=Decimal(str(record.rfid_latency_ms)),
            transaction_time=(
                _SIMULATION_START.replace(hour=record.hour)
                + timedelta(seconds=record.pass_no)
            ),
        )
        transactions.append(transaction)
        if is_exception:
            exceptions.append(ExceptionRecord(
                exception_id=uuid.uuid5(transaction_id, "exception"),
                transaction_id=transaction_id,
                plaza_id=plaza.plaza_id,
                lane_id=transaction.lane_id,
                exception_type=_exception_type(record),
                details=(
                    f"Simulation demo: {scenario}, seed {seed}, pass {record.pass_no}. "
                    f"{record.notes or record.charge_status}"
                ),
            ))

    db.add_all([*transactions, *exceptions])
    db.commit()
    return len(transactions)
