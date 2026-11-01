from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.security import hash_password
from app.database import SessionLocal, init_db
from app.models.device import Device
from app.models.enums import (
    DeviceStatus,
    DeviceType,
    TollingType,
    UserRole,
    VehicleClass,
)
from app.models.highway import Highway
from app.models.plaza import Plaza
from app.models.segment import Segment
from app.models.tariff import Tariff
from app.models.user import User
from app.models.vehicle import Vehicle


def get_or_create(db, model, defaults=None, **lookup):
    instance = db.query(model).filter_by(**lookup).first()
    if instance:
        return instance, False
    params = {**lookup, **(defaults or {})}
    instance = model(**params)
    db.add(instance)
    db.flush()
    return instance, True


def seed():
    init_db()
    db = SessionLocal()
    try:
        # --- Highways -----------------------------------------------------
        highway_open, _ = get_or_create(
            db, Highway,
            nh_number="NH-48-DEMO",
            defaults=dict(
                name="NH 48 Demo Corridor",
                states=["MH", "KA"],
                total_length_km=Decimal("250.00"),
                tolling_type=TollingType.OPEN,
                operator_name="Demo Highway Authority",
            ),
        )
        highway_closed, _ = get_or_create(
            db, Highway,
            nh_number="NH-44-DEMO",
            defaults=dict(
                name="NH 44 Demo Expressway",
                states=["DL", "HR"],
                total_length_km=Decimal("180.00"),
                tolling_type=TollingType.CLOSED,
                operator_name="Demo Expressway Ltd",
            ),
        )
        highway_nh19, _ = get_or_create(
            db, Highway,
            nh_number="NH-19",
            defaults=dict(
                name="NH 19 (Delhi - Kolkata, GT Road)",
                states=["UP", "BR", "WB"],
                total_length_km=Decimal("1435.00"),
                tolling_type=TollingType.OPEN,
                operator_name="NHAI",
            ),
        )
        highway_nh27, _ = get_or_create(
            db, Highway,
            nh_number="NH-27",
            defaults=dict(
                name="NH 27 (East-West Corridor)",
                states=["GJ", "MP", "AS"],
                total_length_km=Decimal("3507.00"),
                tolling_type=TollingType.CLOSED,
                operator_name="NHAI",
            ),
        )

        # --- Plazas ---------------------------------------------------------
        plaza_a, _ = get_or_create(
            db, Plaza,
            plaza_code="PLZ-A",
            defaults=dict(
                highway_id=highway_open.highway_id,
                name="Plaza A (Open Tolling)",
                chainage_km=Decimal("45.00"),
                state_code="MH",
                latitude=Decimal("19.076000"),
                longitude=Decimal("72.877700"),
                num_lanes=8,
                direction="eastbound",
                operator_name="Demo Highway Authority",
                commissioned_on=date(2022, 1, 1),
                is_active=True,
            ),
        )
        plaza_entry, _ = get_or_create(
            db, Plaza,
            plaza_code="PLZ-B-ENTRY",
            defaults=dict(
                highway_id=highway_closed.highway_id,
                name="Plaza B (Closed Entry)",
                chainage_km=Decimal("0.00"),
                state_code="DL",
                num_lanes=6,
                direction="northbound",
                operator_name="Demo Expressway Ltd",
                commissioned_on=date(2023, 6, 1),
                is_active=True,
            ),
        )
        plaza_exit, _ = get_or_create(
            db, Plaza,
            plaza_code="PLZ-C-EXIT",
            defaults=dict(
                highway_id=highway_closed.highway_id,
                name="Plaza C (Closed Exit)",
                chainage_km=Decimal("120.00"),
                state_code="HR",
                num_lanes=6,
                direction="northbound",
                operator_name="Demo Expressway Ltd",
                commissioned_on=date(2023, 6, 1),
                is_active=True,
            ),
        )
        plaza_d, _ = get_or_create(
            db, Plaza,
            plaza_code="PLZ-D",
            defaults=dict(
                highway_id=highway_nh19.highway_id,
                name="Plaza D (NH-19 Open Tolling)",
                chainage_km=Decimal("210.00"),
                state_code="UP",
                num_lanes=10,
                direction="eastbound",
                operator_name="NHAI",
                commissioned_on=date(2021, 4, 1),
                is_active=True,
            ),
        )
        plaza_e_entry, _ = get_or_create(
            db, Plaza,
            plaza_code="PLZ-E-ENTRY",
            defaults=dict(
                highway_id=highway_nh27.highway_id,
                name="Plaza E (NH-27 Closed Entry)",
                chainage_km=Decimal("0.00"),
                state_code="GJ",
                num_lanes=8,
                direction="eastbound",
                operator_name="NHAI",
                commissioned_on=date(2020, 11, 1),
                is_active=True,
            ),
        )
        plaza_f_exit, _ = get_or_create(
            db, Plaza,
            plaza_code="PLZ-F-EXIT",
            defaults=dict(
                highway_id=highway_nh27.highway_id,
                name="Plaza F (NH-27 Closed Exit)",
                chainage_km=Decimal("340.00"),
                state_code="MP",
                num_lanes=8,
                direction="eastbound",
                operator_name="NHAI",
                commissioned_on=date(2020, 11, 1),
                is_active=True,
            ),
        )

        # --- Segments (closed tolling) ----------------------------------------
        segment, _ = get_or_create(
            db, Segment,
            entry_plaza_id=plaza_entry.plaza_id,
            exit_plaza_id=plaza_exit.plaza_id,
            defaults=dict(
                highway_id=highway_closed.highway_id,
                name="Plaza B to Plaza C",
                distance_km=Decimal("120.00"),
                is_active=True,
            ),
        )
        segment_nh27, _ = get_or_create(
            db, Segment,
            entry_plaza_id=plaza_e_entry.plaza_id,
            exit_plaza_id=plaza_f_exit.plaza_id,
            defaults=dict(
                highway_id=highway_nh27.highway_id,
                name="Plaza E to Plaza F",
                distance_km=Decimal("340.00"),
                is_active=True,
            ),
        )

        # --- Tariffs ---------------------------------------------------------
        today = date.today()
        get_or_create(
            db, Tariff,
            plaza_id=plaza_a.plaza_id,
            vehicle_class=VehicleClass.CAR_JEEP_VAN,
            defaults=dict(
                base_fare=Decimal("65.00"),
                return_trip_discount_percent=Decimal("50.00"),
                return_trip_window_hours=24,
                local_resident_discount_percent=Decimal("50.00"),
                night_surcharge_percent=Decimal("0.00"),
                currency="INR",
                effective_from=today,
                notified_by="Demo Highway Authority",
            ),
        )
        get_or_create(
            db, Tariff,
            plaza_id=plaza_a.plaza_id,
            vehicle_class=VehicleClass.BUS_TRUCK,
            defaults=dict(
                base_fare=Decimal("210.00"),
                return_trip_discount_percent=Decimal("0.00"),
                return_trip_window_hours=24,
                local_resident_discount_percent=Decimal("0.00"),
                night_surcharge_percent=Decimal("10.00"),
                currency="INR",
                effective_from=today,
                notified_by="Demo Highway Authority",
            ),
        )
        get_or_create(
            db, Tariff,
            segment_id=segment.segment_id,
            vehicle_class=VehicleClass.CAR_JEEP_VAN,
            defaults=dict(
                base_fare=Decimal("30.00"),
                rate_per_km=Decimal("1.50"),
                return_trip_discount_percent=Decimal("50.00"),
                return_trip_window_hours=24,
                local_resident_discount_percent=Decimal("0.00"),
                night_surcharge_percent=Decimal("0.00"),
                currency="INR",
                effective_from=today,
                notified_by="Demo Expressway Ltd",
            ),
        )
        get_or_create(
            db, Tariff,
            plaza_id=plaza_d.plaza_id,
            vehicle_class=VehicleClass.CAR_JEEP_VAN,
            defaults=dict(
                base_fare=Decimal("75.00"),
                return_trip_discount_percent=Decimal("50.00"),
                return_trip_window_hours=24,
                local_resident_discount_percent=Decimal("50.00"),
                night_surcharge_percent=Decimal("0.00"),
                currency="INR",
                effective_from=today,
                notified_by="NHAI",
            ),
        )
        get_or_create(
            db, Tariff,
            plaza_id=plaza_d.plaza_id,
            vehicle_class=VehicleClass.BUS_TRUCK,
            defaults=dict(
                base_fare=Decimal("245.00"),
                return_trip_discount_percent=Decimal("0.00"),
                return_trip_window_hours=24,
                local_resident_discount_percent=Decimal("0.00"),
                night_surcharge_percent=Decimal("10.00"),
                currency="INR",
                effective_from=today,
                notified_by="NHAI",
            ),
        )
        get_or_create(
            db, Tariff,
            segment_id=segment_nh27.segment_id,
            vehicle_class=VehicleClass.CAR_JEEP_VAN,
            defaults=dict(
                base_fare=Decimal("35.00"),
                rate_per_km=Decimal("1.65"),
                return_trip_discount_percent=Decimal("50.00"),
                return_trip_window_hours=24,
                local_resident_discount_percent=Decimal("0.00"),
                night_surcharge_percent=Decimal("0.00"),
                currency="INR",
                effective_from=today,
                notified_by="NHAI",
            ),
        )
        get_or_create(
            db, Tariff,
            segment_id=segment_nh27.segment_id,
            vehicle_class=VehicleClass.BUS_TRUCK,
            defaults=dict(
                base_fare=Decimal("90.00"),
                rate_per_km=Decimal("4.20"),
                return_trip_discount_percent=Decimal("0.00"),
                return_trip_window_hours=24,
                local_resident_discount_percent=Decimal("0.00"),
                night_surcharge_percent=Decimal("10.00"),
                currency="INR",
                effective_from=today,
                notified_by="NHAI",
            ),
        )

        # --- Vehicles ----------------------------------------------------------
        vehicle_car, _ = get_or_create(
            db, Vehicle,
            plate_number="MH12AB1234",
            defaults=dict(
                registration_state="MH",
                vehicle_class=VehicleClass.CAR_JEEP_VAN,
                fastag_id="FASTAG-DEMO-0001",
                fastag_issuer_bank="Demo Bank",
                is_commercial=False,
            ),
        )
        vehicle_truck, _ = get_or_create(
            db, Vehicle,
            plate_number="DL1LT5678",
            defaults=dict(
                registration_state="DL",
                vehicle_class=VehicleClass.BUS_TRUCK,
                fastag_id="FASTAG-DEMO-0002",
                fastag_issuer_bank="Demo Bank",
                is_commercial=True,
            ),
        )

        # --- Devices -------------------------------------------------------------
        get_or_create(
            db, Device,
            name="Plaza A - Lane 1 Front Camera",
            defaults=dict(
                device_type=DeviceType.CAMERA_FRONT,
                plaza_id=plaza_a.plaza_id,
                lane_id="L1",
                status=DeviceStatus.ONLINE,
                error_count_24h=0,
                avg_latency_ms=Decimal("120.00"),
                last_heartbeat_at=datetime.now(timezone.utc),
            ),
        )
        get_or_create(
            db, Device,
            name="Plaza A - Lane 1 RFID Reader",
            defaults=dict(
                device_type=DeviceType.RFID_READER,
                plaza_id=plaza_a.plaza_id,
                lane_id="L1",
                status=DeviceStatus.ONLINE,
                error_count_24h=0,
                avg_latency_ms=Decimal("45.00"),
                last_heartbeat_at=datetime.now(timezone.utc),
            ),
        )

        # --- Users ---------------------------------------------------------------
        get_or_create(
            db, User,
            username="admin",
            defaults=dict(
                hashed_password=hash_password("admin123"),
                role=UserRole.ADMIN,
                is_active=True,
            ),
        )
        get_or_create(
            db, User,
            username="operator1",
            defaults=dict(
                hashed_password=hash_password("operator123"),
                role=UserRole.OPERATOR,
                is_active=True,
            ),
        )

        db.commit()
        print("Seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()