from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal, init_db
from app.models.plaza import Plaza
from app.models.segment import Segment
from app.models.trip import Trip
from app.models.vehicle import Vehicle
from app.toll import TariffNotFoundError, TollCalculator


def print_transaction(label: str, transaction) -> None:
    print(f"\n--- {label} ---")
    print("base_amount:    ", transaction.base_amount)
    print("discount_amount:", transaction.discount_amount)
    print("surcharge_amount:", transaction.surcharge_amount)
    print("amount_charged: ", transaction.amount_charged)
    print("applied_rules:")
    for rule in transaction.applied_rules:
        print("   ", rule)


def main():
    init_db()
    db = SessionLocal()
    try:
        calculator = TollCalculator(db)

        # --- Open tolling: Plaza A, car, daytime, no return trip ---------
        vehicle_car = db.query(Vehicle).filter_by(plate_number="MH12AB1234").first()
        plaza_a = db.query(Plaza).filter_by(plaza_code="PLZ-A").first()

        trip_open = Trip(
            vehicle_id=vehicle_car.vehicle_id,
            entry_plaza_id=plaza_a.plaza_id,
            entry_time=datetime(2026, 10, 15, 14, 0, tzinfo=timezone.utc),
        )
        db.add(trip_open)
        db.flush()

        txn_open = calculator.calculate(trip_open, vehicle_car)
        print_transaction("Open tolling - Plaza A, car, daytime", txn_open)

        # --- Closed tolling: Plaza B -> Plaza C segment, truck ------------
               # --- Closed tolling: Plaza E -> Plaza F segment (NH-27), truck ----
        vehicle_truck = db.query(Vehicle).filter_by(plate_number="DL1LT5678").first()
        segment = db.query(Segment).filter_by(name="Plaza E to Plaza F").first()

        entry_time = datetime(2026, 10, 15, 23, 30, tzinfo=timezone.utc)  # within night window
        trip_closed = Trip(
            vehicle_id=vehicle_truck.vehicle_id,
            segment_id=segment.segment_id,
            entry_plaza_id=segment.entry_plaza_id,
            entry_time=entry_time,
            exit_plaza_id=segment.exit_plaza_id,
            exit_time=entry_time + timedelta(hours=2),
            distance_travelled_km=segment.distance_km,
        )
        db.add(trip_closed)
        db.flush()

        txn_closed = calculator.calculate(trip_closed, vehicle_truck)
        print_transaction("Closed tolling - Plaza E to F (NH-27), truck, night surcharge", txn_closed)

        # --- Missing tariff: a vehicle class/scope with no tariff row ----
        try:
            bad_trip = Trip(
                vehicle_id=vehicle_car.vehicle_id,
                entry_plaza_id=plaza_a.plaza_id,
                entry_time=datetime(2020, 1, 1, tzinfo=timezone.utc),  # before any tariff's effective_from
            )
            db.add(bad_trip)
            db.flush()
            calculator.calculate(bad_trip, vehicle_car)
            print("\n--- Missing tariff test FAILED: expected TariffNotFoundError ---")
        except TariffNotFoundError as exc:
            print("\n--- Missing tariff test passed ---")
            print("Raised as expected:", exc)

    finally:
        db.rollback()  # dry run only — do not persist test trips/transactions
        db.close()


if __name__ == "__main__":
    main()