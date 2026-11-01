"""Configurable toll policy engine (P3).

Loads plaza rate configuration from YAML and computes a toll amount for
a given vehicle class + context, producing a full, auditable list of
which rules fired — stored verbatim on the Transaction record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

from app.models.enums import VehicleClass

DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "toll_rates.yaml"


@dataclass
class TollContext:
    """Everything the policy engine needs to know about *this* pass,
    beyond the base vehicle class."""

    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_local_resident: bool = False
    is_return_trip_within_window: bool = False
    tag_not_found: bool = False


@dataclass
class TollComputation:
    plaza_id: str
    vehicle_class: str
    base_rate: float
    time_of_day_multiplier: float
    discount_percent: float
    surcharge_percent: float
    amount_charged: float
    applied_rules: list[str]
    currency: str = "INR"


_CONDITION_CHECKS = {
    "vehicle.is_local_resident": lambda ctx: ctx.is_local_resident,
    "return_trip": lambda ctx: ctx.is_return_trip_within_window,
    "exception.tag_not_found": lambda ctx: ctx.tag_not_found,
}


class PolicyEngine:
    def __init__(self, config_path: Path | str = DEFAULT_CONFIG_PATH):
        self.config_path = Path(config_path)
        self._config = self._load_config()

    def _load_config(self) -> dict:
        with open(self.config_path, "r") as f:
            return yaml.safe_load(f)

    def reload(self) -> None:
        """Hot-reload config without restarting the service."""
        self._config = self._load_config()

    def _plaza_config(self, plaza_id: str) -> dict:
        plazas = self._config.get("plazas", {})
        if plaza_id in plazas:
            return plazas[plaza_id]
        return next(iter(plazas.values()))

    def compute(
        self,
        plaza_id: str,
        vehicle_class: VehicleClass,
        context: TollContext | None = None,
    ) -> TollComputation:
        context = context or TollContext()
        plaza = self._plaza_config(plaza_id)
        applied_rules: list[str] = []

        base_rate = float(plaza["base_rates"].get(vehicle_class.value, plaza["base_rates"]["unknown"]))

        # Time-of-day multiplier
        multiplier = 1.0
        hour = context.timestamp.hour
        for rule in plaza.get("time_of_day_rules", []):
            start, end = rule["start_hour"], rule["end_hour"]
            in_window = (start <= hour or hour < end) if start > end else (start <= hour < end)
            if in_window and rule["multiplier"] != 1.0:
                multiplier = rule["multiplier"]
                applied_rules.append(f"time_of_day:{rule['name']}(x{multiplier})")

        # Discounts (first match wins)
        discount_percent = 0.0
        for rule in plaza.get("discount_rules", []):
            check = _CONDITION_CHECKS.get(rule["condition"])
            if check and check(context):
                discount_percent = float(rule["discount_percent"])
                applied_rules.append(f"discount:{rule['name']}(-{discount_percent}%)")
                break

        # Surcharges (all matches stack)
        surcharge_percent = 0.0
        for rule in plaza.get("surcharge_rules", []):
            check = _CONDITION_CHECKS.get(rule["condition"])
            if check and check(context):
                pct = float(rule["surcharge_percent"])
                surcharge_percent += pct
                applied_rules.append(f"surcharge:{rule['name']}(+{pct}%)")

        amount = base_rate * multiplier
        amount -= amount * (discount_percent / 100.0)
        amount += amount * (surcharge_percent / 100.0)
        amount = round(max(amount, 0.0), 2)

        if not applied_rules:
            applied_rules.append("base_rate_only")

        return TollComputation(
            plaza_id=plaza_id,
            vehicle_class=vehicle_class.value,
            base_rate=base_rate,
            time_of_day_multiplier=multiplier,
            discount_percent=discount_percent,
            surcharge_percent=surcharge_percent,
            amount_charged=amount,
            applied_rules=applied_rules,
            currency=plaza.get("currency", "INR"),
        )