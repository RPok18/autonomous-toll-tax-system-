from __future__ import annotations

import sys
from datetime import date

from app.core.security import hash_password
from app.database import SessionLocal, init_db
from app.models.enums import TollingType, UserRole, VehicleClass
from app.models.highway import Highway
from app.models.plaza import Plaza
from app.models.segment import Segment
from app.models.tariff import Tariff
from app.models.user import User
from app.models.vehicle import Vehicle

# Base fares mirror backend/app/policy/config/toll_rates.yaml (plaza-01) so
# the YAML-driven policy engine and the DB tariffs tell the same story
# until PolicyEngine is switched to read tariffs directly (see roadmap).
OPEN_TOLLING_BASE_FARES: dict[VehicleClass, float] = {
    VehicleClass.TWO_WHEELER: 0,
    VehicleClass.CAR_JEEP_VAN: 65,
    VehicleClass.LCV: 105,
    VehicleClass.BUS_TRUCK: 220,
    VehicleClass.HCV_MAV: 355,
    VehicleClass.OVERSIZED: 690,
    VehicleClass.EXEMPT_OTHER: 0,
    VehicleClass.UNKNOWN: 65,
}

# Per-km rates for the closed/distance-based demo segment.
SEGMENT_RATE_PER_KM: dict[VehicleClass, float] = {
    VehicleClass.TWO_WHEELER: 0,
    VehicleClass.CAR_JEEP_VAN: 2.5,
    VehicleClass.LCV: 4.0,
    VehicleClass.BUS_TRUCK: 8.0,
    VehicleClass.HCV_MAV: 12.0,
    VehicleClass.OVERSIZED: 18.0,
    VehicleClass.EXEMPT_OTHER: 0,
    VehicleClass.UNKNOWN: 2.5,
}

EFFECTIVE_FROM = date(2025, 1, 1)

DEMO_VEHICLES = [
    # plate_number, fastag_id, vehicle_class, is_commercial
    ("MH12AB1234", "TAG1000000001", VehicleClass.CAR_JEEP_VAN, False),
    ("DL1CAB5678", "TAG1000000002", VehicleClass.CAR_JEEP_VAN, False),
    ("KA05MZ4321", None, VehicleClass.TWO_WHEELER, False),
    ("GJ01BT9999", "TAG1000000004", VehicleClass.BUS_TRUCK, True),
    ("RJ14HC1111", "TAG1000000005", VehicleClass.HCV_MAV, True),
    ("UP32LC2222", "TAG1000000006", VehicleClass.LCV, True),
]


def get_or_create_highway(db, nh_number: str, **kwargs) -> Highway:
    highway = db.query(Highway).filter(Highway.nh_number == nh_number).first()
    if highway is None:
        highway = Highway(nh_number=nh_number, **kwargs)
        db.add(highway)
        db.flush()
        print(f"  + highway {nh_number}")
    return highway


def get_or_create_plaza(db, plaza_code: str, **kwargs) -> Plaza:
    plaza = db.query(Plaza).filter(Plaza.plaza_code == plaza_code).first()
    if plaza is None:
        plaza = Plaza(plaza_code=plaza_code, **kwargs)
        db.add(plaza)
        db.flush()
        print(f"  + plaza {plaza_code}")
    return plaza


def get_or_create_segment(db, entry_plaza_id, exit_plaza_id, **kwargs) -> Segment:
    segment = (
        db.query(Segment)
        .filter(Segment.entry_plaza_id == entry_plaza_id, Segment.exit_plaza_id == exit_plaza_id)
        .first()
    )
    if segment is None:
        segment = Segment(entry_plaza_id=entry_plaza_id, exit_plaza_id=exit_plaza_id, **kwargs)
        db.add(segment)
        db.flush()
        print(f"  + segment {kwargs.get('name', entry_plaza_id)}")
    return segment


def seed_plaza_tariffs(db, plaza: Plaza) -> None:
    for vclass, fare in OPEN_TOLLING_BASE_FARES.items():
        exists = (
            db.query(Tariff)
            .filter(Tariff.plaza_id == plaza.plaza_id, Tariff.vehicle_class == vclass, Tariff.effective_to.is_(None))
            .first()
        )
        if exists:
            continue
        db.add(Tariff(
            plaza_id=plaza.plaza_id,
            vehicle_class=vclass,
            base_fare=fare,
            return_trip_discount_percent=100 if vclass == VehicleClass.CAR_JEEP_VAN else 0,
            return_trip_window_hours=24,
            local_resident_discount_percent=50,
            effective_from=EFFECTIVE_FROM,
            notified_by="Demo seed data — not a real NHAI notification",
        ))
    print(f"  + tariffs for plaza {plaza.plaza_code}")


def seed_segment_tariffs(db, segment: Segment) -> None:
    for vclass, rate in SEGMENT_RATE_PER_KM.items():
        exists = (
            db.query(Tariff)
            .filter(Tariff.segment_id == segment.segment_id, Tariff.vehicle_class == vclass, Tariff.effective_to.is_(None))
            .first()
        )
        if exists:
            continue
        db.add(Tariff(
            segment_id=segment.segment_id,
            vehicle_class=vclass,
            base_fare=0,
            rate_per_km=rate,
            effective_from=EFFECTIVE_FROM,
            notified_by="Demo seed data — not a real NHAI notification",
        ))
    print(f"  + tariffs for segment {segment.name}")


def seed_vehicles(db) -> None:
    for plate, tag, vclass, is_commercial in DEMO_VEHICLES:
        if db.query(Vehicle).filter(Vehicle.plate_number == plate).first():
            continue
        db.add(Vehicle(
            plate_number=plate,
            fastag_id=tag,
            vehicle_class=vclass,
            is_commercial=is_commercial,
            registration_state=plate[:2],
        ))
        print(f"  + vehicle {plate}")


def seed_users(db) -> None:
    demo_users = [
        ("admin", "admin123", UserRole.ADMIN),
        ("operator1", "operator123", UserRole.OPERATOR),
    ]
    for username, password, role in demo_users:
        if db.query(User).filter(User.username == username).first():
            continue
        db.add(User(username=username, hashed_password=hash_password(password), role=role))
        print(f"  + user {username} ({role.value})")


def main() -> None:
    print("Ensuring tables exist...")
    init_db()

    db = SessionLocal()
    try:
        print("Seeding open-tolling highway + plazas...")
        nh48 = get_or_create_highway(
            db, "NH-48-DEMO",
            name="Delhi-Mumbai Demo Corridor", states=["DL", "HR", "RJ", "MP", "GJ", "MH"],
            total_length_km=1350, tolling_type=TollingType.OPEN, operator_name="NHAI (demo)",
        )
        plaza_01 = get_or_create_plaza(
            db, "plaza-01", highway_id=nh48.highway_id, name="NH-Demo Plaza 01",
            chainage_km=42.0, state_code="HR", latitude=28.4595, longitude=77.0266,
            num_lanes=8, direction="both", operator_name="NHAI (demo)",
        )
        plaza_02 = get_or_create_plaza(
            db, "plaza-02", highway_id=nh48.highway_id, name="NH-Demo Plaza 02",
            chainage_km=210.0, state_code="RJ", latitude=27.0238, longitude=74.2179,
            num_lanes=6, direction="both", operator_name="NHAI (demo)",
        )
        seed_plaza_tariffs(db, plaza_01)
        seed_plaza_tariffs(db, plaza_02)

        print("Seeding closed/distance-based expressway + segment...")
        expwy = get_or_create_highway(
            db, "EXPWY-DEMO", name="Demo Access-Controlled Expressway", states=["MH"],
            total_length_km=120, tolling_type=TollingType.CLOSED, operator_name="State Expressway Authority (demo)",
        )
        entry_plaza = get_or_create_plaza(
            db, "expwy-entry-a", highway_id=expwy.highway_id, name="Expwy Entry A",
            chainage_km=0.0, state_code="MH", num_lanes=4, direction="entry", operator_name="Demo Concessionaire",
        )
        exit_plaza = get_or_create_plaza(
            db, "expwy-exit-b", highway_id=expwy.highway_id, name="Expwy Exit B",
            chainage_km=120.0, state_code="MH", num_lanes=4, direction="exit", operator_name="Demo Concessionaire",
        )
        segment = get_or_create_segment(
            db, entry_plaza.plaza_id, exit_plaza.plaza_id,
            highway_id=expwy.highway_id, name="Entry A -> Exit B", distance_km=120.0,
        )
        seed_segment_tariffs(db, segment)

        print("Seeding demo vehicles...")
        seed_vehicles(db)

        print("Seeding demo users...")
        seed_users(db)

        db.commit()
        print("Done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.path.insert(0, ".")  # allow `python scripts/seed.py` from backend/ without -m
    main()