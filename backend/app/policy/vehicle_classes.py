"""Helpers for working with Indian tolling vehicle classes.

Actual class *detection* (from an ANPR crop, or a future vehicle
classifier) is out of scope here; class comes from the vehicle registry
or an explicit operator override."""
from __future__ import annotations

from app.models.enums import VehicleClass

VEHICLE_CLASS_LABELS: dict[VehicleClass, str] = {
    VehicleClass.TWO_WHEELER: "Two-Wheeler (exempt)",
    VehicleClass.CAR_JEEP_VAN: "Car / Jeep / Van",
    VehicleClass.LCV: "Light Commercial Vehicle",
    VehicleClass.BUS_TRUCK: "Bus / Truck",
    VehicleClass.HCV_MAV: "Heavy / Multi-Axle Vehicle",
    VehicleClass.OVERSIZED: "Oversized / Special",
    VehicleClass.EXEMPT_OTHER: "Exempt (Govt./Emergency/etc.)",
    VehicleClass.UNKNOWN: "Unclassified",
}


def is_exempt(vehicle_class: VehicleClass) -> bool:
    return vehicle_class in (VehicleClass.TWO_WHEELER, VehicleClass.EXEMPT_OTHER)