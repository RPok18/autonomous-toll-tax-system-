"""Pass-level simulation: ANPR + RFID + FusionEngine + PolicyEngine + a ledger.

`process_pass` handles ONE vehicle pass given the two signals, so the four
per-vehicle cases in the article can be tested with hand-built signals.
`run_scenario` draws many passes from the simulators with a fixed seed.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.anpr.reader import ANPRSignal
from app.anpr.simulator import ANPRSimulator
from app.fusion.fusion_engine import FusionEngine
from app.models.enums import VehicleClass
from app.policy.rules_engine import PolicyEngine, TollContext
from app.rfid.simulator import RFIDReadResult, RFIDSimulator
from app.simulation.scenarios import Scenario

PLAZA_ID = "plaza-01"
POOL_SIZE = 500
START_BALANCE = Decimal("1000000.00")
CLASS_MIX = (
    (VehicleClass.CAR_JEEP_VAN, 0.70),
    (VehicleClass.LCV, 0.10),
    (VehicleClass.BUS_TRUCK, 0.10),
    (VehicleClass.HCV_MAV, 0.05),
    (VehicleClass.TWO_WHEELER, 0.05),
)


def normalise_plate(plate: str | None) -> str | None:
    return None if plate is None else "".join(plate.split()).upper()


@dataclass
class SimVehicle:
    plate: str
    tag_id: str
    vehicle_class: VehicleClass
    balance: Decimal


class Registry:
    """In-memory stand-in for the vehicles table and its balances."""

    def __init__(self, vehicles: list[SimVehicle]):
        self.vehicles = vehicles
        self.by_plate = {normalise_plate(v.plate): v for v in vehicles}
        self.tag_owner = {v.tag_id: v for v in vehicles}

    @property
    def known_tag_ids(self) -> set[str]:
        return set(self.tag_owner)

    def plate_for_tag(self, tag_id: str | None) -> str | None:
        owner = self.tag_owner.get(tag_id) if tag_id else None
        return owner.plate if owner else None


def build_registry(seed: int, low_balance_share: float = 0.0) -> Registry:
    rng = random.Random(seed + 7)
    classes, weights = zip(*CLASS_MIX)
    vehicles = []
    for i in range(POOL_SIZE):
        plate = f"MH12AB{1000 + i}"
        balance = Decimal("0.00") if rng.random() < low_balance_share else START_BALANCE
        vehicles.append(SimVehicle(plate, f"TAG{plate}", rng.choices(classes, weights)[0], balance))
    return Registry(vehicles)


@dataclass
class PassRecord:
    pass_no: int = 0
    true_plate: str = ""
    carried_tag: str | None = None
    vehicle_class: str = ""
    hour: int = 12
    anpr_plate: str | None = None
    anpr_confidence: float = 0.0
    rfid_tag: str | None = None
    rfid_confidence: float = 0.0
    rfid_latency_ms: float = 0.0
    method: str = ""
    resolved_plate: str | None = None
    fusion_exception: bool = False
    notes: str = ""
    outcome: str = ""            # correct | wrong | unresolved
    silent_wrong: bool = False   # wrong plate and no exception flag
    charge_status: str = ""      # paid | unresolved | held_exception | no_vehicle | insufficient_balance
    expected_amount: float = 0.0
    charged_amount: float = 0.0
    charged_to_true_vehicle: bool = False
    balance_delta_ok: bool = False
    decision_ms: float = 0.0


def process_pass(
    *,
    engine: FusionEngine,
    policy: PolicyEngine,
    registry: Registry,
    true_vehicle: SimVehicle,
    anpr: ANPRSignal,
    rfid: RFIDReadResult,
    carried_tag: str | None = None,
    context: TollContext | None = None,
    plaza_id: str = PLAZA_ID,
    pass_no: int = 0,
) -> PassRecord:
    """One pass: identify, compute the toll, and charge the ledger.

    A pass is charged only when the vehicle is identified and no exception is
    raised. Flagged passes are held for manual review and are not charged.
    """
    context = context or TollContext(timestamp=datetime(2026, 10, 1, 12))
    started = time.perf_counter()

    registered_plate = registry.plate_for_tag(rfid.tag_id) if (rfid.tag_id and rfid.tag_registered) else None
    result = engine.resolve(anpr, rfid, registered_plate)
    expected = Decimal(str(policy.compute(plaza_id, true_vehicle.vehicle_class, context).amount_charged))

    resolved = normalise_plate(result.plate_number)
    true_plate = normalise_plate(true_vehicle.plate)
    if resolved is None:
        outcome = "unresolved"
    elif resolved == true_plate:
        outcome = "correct"
    else:
        outcome = "wrong"

    charged = Decimal("0.00")
    to_true = False
    delta_ok = False
    if resolved is None:
        status = "unresolved"
    elif result.is_exception:
        status = "held_exception"
    else:
        target = registry.by_plate.get(resolved)
        if target is None:
            status = "no_vehicle"
        else:
            amount = Decimal(str(policy.compute(plaza_id, target.vehicle_class, context).amount_charged))
            if target.balance < amount:
                status = "insufficient_balance"
            else:
                before = target.balance
                target.balance -= amount
                charged = amount
                status = "paid"
                to_true = target is true_vehicle
                delta_ok = (before - target.balance) == amount

    decision_ms = (time.perf_counter() - started) * 1000.0
    return PassRecord(
        pass_no=pass_no,
        true_plate=true_vehicle.plate,
        carried_tag=carried_tag,
        vehicle_class=true_vehicle.vehicle_class.value,
        hour=context.timestamp.hour,
        anpr_plate=anpr.plate_number,
        anpr_confidence=anpr.confidence,
        rfid_tag=rfid.tag_id,
        rfid_confidence=rfid.confidence,
        rfid_latency_ms=round(rfid.read_latency_ms, 3),
        method=result.identification_method.value,
        resolved_plate=result.plate_number,
        fusion_exception=result.is_exception,
        notes=";".join(result.notes),
        outcome=outcome,
        silent_wrong=(outcome == "wrong" and not result.is_exception),
        charge_status=status,
        expected_amount=float(expected),
        charged_amount=float(charged),
        charged_to_true_vehicle=to_true,
        balance_delta_ok=delta_ok,
        decision_ms=round(decision_ms, 4),
    )


@dataclass
class _Settings:
    anpr_min_confidence: float
    rfid_min_confidence: float
    fusion_primary_signal: str
    fusion_mode: str = "hybrid"


def run_scenario(scenario: Scenario, seed: int, passes: int) -> list[PassRecord]:
    """Run one scenario with one seed. Same scenario and seed give the same
    identification results (only the timing columns differ between runs)."""
    if passes < 0:
        raise ValueError("passes must not be negative")

    settings = _Settings(
        anpr_min_confidence=scenario.anpr_min_confidence,
        rfid_min_confidence=scenario.rfid_min_confidence,
        fusion_primary_signal=scenario.primary_signal,
        fusion_mode=scenario.fusion_mode,
    )
    engine = FusionEngine(settings=settings)
    policy = PolicyEngine()
    anpr_sim = ANPRSimulator(seed=seed, **scenario.anpr)
    rfid_sim = RFIDSimulator(seed=seed, **scenario.rfid)
    registry = build_registry(seed, scenario.low_balance_share)
    known_tags = registry.known_tag_ids
    plates = [v.plate for v in registry.vehicles]

    traffic_rng = random.Random(seed + 99)
    hour_rng = random.Random(seed + 1234)
    records: list[PassRecord] = []

    for n in range(passes):
        vehicle = registry.by_plate[traffic_rng.choice(plates)]
        carried = vehicle.tag_id if traffic_rng.random() < scenario.tag_share else None
        if carried is not None and traffic_rng.random() < scenario.clone_share:
            other = traffic_rng.choice([p for p in plates if p != vehicle.plate])
            carried = registry.by_plate[other].tag_id

        anpr = anpr_sim.simulate_read(vehicle.plate)
        rfid = rfid_sim.simulate_pass(carried, known_tags)
        context = TollContext(timestamp=datetime(2026, 10, 1, hour_rng.randrange(24)))
        records.append(process_pass(
            engine=engine, policy=policy, registry=registry, true_vehicle=vehicle,
            anpr=anpr, rfid=rfid, carried_tag=carried, context=context, pass_no=n,
        ))
    return records
