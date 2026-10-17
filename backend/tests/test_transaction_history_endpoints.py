from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api import transactions as transaction_api
from app.models.enums import PaymentStatus
from app.models.transaction import Transaction


class FakeQuery:
    def __init__(self, results):
        self.results = results
        self.filters = {}
        self.criteria = []
        self.ordering = ()
        self.offset_value = None
        self.limit_value = None

    def filter_by(self, **filters):
        self.filters.update(filters)
        return self

    def filter(self, criterion):
        self.criteria.append(criterion)
        return self

    def order_by(self, *ordering):
        self.ordering = ordering
        return self

    def offset(self, offset):
        self.offset_value = offset
        return self

    def limit(self, limit):
        self.limit_value = limit
        return self

    def all(self):
        return self.results


class FakeSession:
    def __init__(self, results):
        self.query_result = FakeQuery(results)

    def query(self, model):
        assert model is Transaction
        return self.query_result


def test_transaction_history_filters_and_paginates():
    vehicle_id = uuid.uuid4()
    plaza_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    transactions = [SimpleNamespace(transaction_id=uuid.uuid4())]
    db = FakeSession(transactions)

    result = transaction_api.list_transactions(
        vehicle_id=vehicle_id,
        plate_number="mh 12-ab 1234",
        plaza_id=plaza_id,
        payment_status=PaymentStatus.PAID,
        is_exception=False,
        start_time=now - timedelta(days=1),
        end_time=now,
        limit=20,
        offset=10,
        db=db,
    )

    assert result == transactions
    assert db.query_result.filters == {
        "vehicle_id": vehicle_id,
        "plate_number": "MH12AB1234",
        "plaza_id": plaza_id,
        "payment_status": PaymentStatus.PAID,
        "is_exception": False,
    }
    assert len(db.query_result.criteria) == 2
    assert len(db.query_result.ordering) == 2
    assert db.query_result.offset_value == 10
    assert db.query_result.limit_value == 20


def test_vehicle_transaction_history_filters_by_vehicle_and_status():
    vehicle_id = uuid.uuid4()
    transactions = [SimpleNamespace(transaction_id=uuid.uuid4())]
    db = FakeSession(transactions)

    result = transaction_api.list_vehicle_transactions(
        vehicle_id=vehicle_id,
        plaza_id=None,
        payment_status=PaymentStatus.FAILED,
        is_exception=True,
        start_time=None,
        end_time=None,
        limit=50,
        offset=0,
        db=db,
    )

    assert result == transactions
    assert db.query_result.filters == {
        "vehicle_id": vehicle_id,
        "payment_status": PaymentStatus.FAILED,
        "is_exception": True,
    }
    assert db.query_result.offset_value == 0
    assert db.query_result.limit_value == 50


def test_transaction_history_rejects_reversed_time_range():
    now = datetime.now(timezone.utc)

    with pytest.raises(HTTPException) as exc_info:
        transaction_api.list_transactions(
            start_time=now,
            end_time=now - timedelta(seconds=1),
            limit=50,
            offset=0,
            db=FakeSession([]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "start_time must be before or equal to end_time"


def test_transaction_history_rejects_timezone_naive_range():
    with pytest.raises(HTTPException) as exc_info:
        transaction_api.list_transactions(
            start_time=datetime(2026, 1, 1),
            limit=50,
            offset=0,
            db=FakeSession([]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "start_time must include a timezone"


def test_transaction_history_rejects_empty_normalized_plate():
    with pytest.raises(HTTPException) as exc_info:
        transaction_api.list_transactions(
            plate_number=" --- ",
            limit=50,
            offset=0,
            db=FakeSession([]),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "plate_number must contain letters or digits"
