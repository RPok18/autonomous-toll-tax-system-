"""A6: simultaneous charges against one balance must never take it below zero.

Each request runs in its own thread with its own client and database session.
The toll calculation is slowed down (inside the row lock) so that, without the
row lock in ``charge_vehicle``, every request would read the original balance
before any of them wrote: the test then fails with a lost update instead of
passing by luck of timing.
"""
from __future__ import annotations

import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api import vehicles as vehicle_api
from app.models.transaction import Transaction
from app.models.vehicle import Vehicle
from helpers import add_vehicle


@pytest.fixture()
def slow_calculator(monkeypatch):
    real = vehicle_api.TollCalculator

    class SlowTollCalculator(real):
        def calculate(self, *args, **kwargs):
            transaction = super().calculate(*args, **kwargs)
            time.sleep(0.3)  # widen the race window
            return transaction

    monkeypatch.setattr(vehicle_api, "TollCalculator", SlowTollCalculator)


def fire(app, headers, count: int) -> list[int]:
    barrier = threading.Barrier(count)

    def one_request(_):
        # No "with": entering the client would run the app's startup hook against the dev database.
        client = TestClient(app, raise_server_exceptions=False)
        barrier.wait(timeout=10)
        response = client.post(
            "/vehicles/charge",
            json={"plate_number": "MH12AB1234", "plaza_code": "PLZ-T1"},
            headers=headers,
        )
        return response.status_code

    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(one_request, range(count)))


def final_state(db, vehicle):
    db.expire_all()
    return (
        db.get(Vehicle, vehicle.vehicle_id).balance,
        db.query(Transaction).filter_by(vehicle_id=vehicle.vehicle_id).count(),
    )


def test_two_charges_for_one_balance_only_one_succeeds(app_with_db, auth, db, seed, slow_calculator):
    vehicle = add_vehicle(db, balance="100.00")  # one toll is 65.00, two would need 130.00

    statuses = fire(app_with_db, auth("operator"), 2)

    assert Counter(statuses) == {201: 1, 402: 1}
    balance, transactions = final_state(db, vehicle)
    assert balance == Decimal("35.00")
    assert transactions == 1


def test_many_charges_never_overdraw(app_with_db, auth, db, seed, slow_calculator):
    vehicle = add_vehicle(db, balance="200.00")  # enough for 3 tolls (195.00), not 5

    statuses = fire(app_with_db, auth("operator"), 5)

    assert Counter(statuses) == {201: 3, 402: 2}
    balance, transactions = final_state(db, vehicle)
    assert balance == Decimal("5.00")
    assert transactions == 3


def test_charges_that_all_fit_are_all_applied(app_with_db, auth, db, seed, slow_calculator):
    vehicle = add_vehicle(db, balance="260.00")  # exactly 4 tolls

    statuses = fire(app_with_db, auth("operator"), 4)

    assert statuses == [201, 201, 201, 201]
    balance, transactions = final_state(db, vehicle)
    assert balance == Decimal("0.00")
    assert transactions == 4
