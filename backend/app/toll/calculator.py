from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.models.enums import IdentificationMethod, PaymentStatus, VehicleClass
from app.models.plaza import Plaza
from app.models.tariff import Tariff
from app.models.transaction import Transaction
from app.models.trip import Trip
from app.models.vehicle import Vehicle
from app.policy.rules_engine import PolicyEngine, TollContext

# Standard night-surcharge window used by most Indian toll plazas.
NIGHT_START = time(22, 0)
NIGHT_END = time(6, 0)


class TariffNotFoundError(Exception):
    """Raised when no tariff row covers the trip's scope, vehicle class,
    and date. The caller decides whether to retry, flag an exception
    record, or fall back to a default — this service does not guess."""


class TollCalculator:
    """Computes the fare for a completed (or completing) trip and builds
    the corresponding Transaction row. Does not commit — the caller owns
    the session/transaction boundary.
    """

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def calculate_simulated_amount(
        policy: PolicyEngine,
        plaza_id: str,
        vehicle_class: VehicleClass,
        context: TollContext,
    ) -> Decimal:
        """Return the configured policy amount for a simulated vehicle pass."""
        return Decimal(str(policy.compute(plaza_id, vehicle_class, context).amount_charged))

    def calculate(
        self,
        trip: Trip,
        vehicle: Vehicle,
        *,
        lane_id: str = "AUTO",
        identification_method: IdentificationMethod = IdentificationMethod.UNRESOLVED,
        plate_confidence: Decimal | None = None,
        tag_id: str | None = None,
        tag_confidence: Decimal | None = None,
    ) -> Transaction:
        charge_time = trip.exit_time or trip.entry_time
        charge_date = charge_time.date()

        tariff = self._resolve_tariff(trip, vehicle, charge_date)

        base_amount = self._compute_base_amount(trip, tariff)

        applied_rules: list[dict] = [
            {
                "rule": "base_tariff",
                "tariff_id": str(tariff.tariff_id),
                "base_fare": str(tariff.base_fare),
                "rate_per_km": str(tariff.rate_per_km) if tariff.rate_per_km else None,
                "base_amount": str(base_amount),
            }
        ]

        discount_amount = Decimal("0")

        return_discount = self._return_trip_discount(trip, vehicle, tariff, base_amount, charge_time)
        if return_discount:
            discount_amount += return_discount["amount"]
            applied_rules.append(return_discount)

        resident_discount = self._local_resident_discount(trip, vehicle, tariff, base_amount)
        if resident_discount:
            discount_amount += resident_discount["amount"]
            applied_rules.append(resident_discount)

        # Discounts can never exceed the base amount.
        discount_amount = min(discount_amount, base_amount)

        surcharge_amount = Decimal("0")
        night_surcharge = self._night_surcharge(tariff, base_amount, charge_time)
        if night_surcharge:
            surcharge_amount += night_surcharge["amount"]
            applied_rules.append(night_surcharge)

        amount_charged = base_amount - discount_amount + surcharge_amount
        if amount_charged < 0:
            amount_charged = Decimal("0")

        charging_plaza_id = trip.exit_plaza_id or trip.entry_plaza_id

        return Transaction(
            plaza_id=charging_plaza_id,
            lane_id=lane_id,
            trip_id=trip.trip_id,
            vehicle_id=vehicle.vehicle_id,
            tariff_id=tariff.tariff_id,
            plate_number=vehicle.plate_number,
            plate_confidence=plate_confidence,
            tag_id=tag_id,
            tag_confidence=tag_confidence,
            identification_method=identification_method,
            vehicle_class=vehicle.vehicle_class,
            base_amount=base_amount,
            discount_amount=discount_amount,
            surcharge_amount=surcharge_amount,
            amount_charged=amount_charged,
            currency=tariff.currency,
            payment_status=PaymentStatus.PENDING,
            applied_rules=applied_rules,
            is_exception=False,
        )

    def _resolve_tariff(self, trip: Trip, vehicle: Vehicle, charge_date: date) -> Tariff:
        if trip.segment_id is not None:
            scope_filter = Tariff.segment_id == trip.segment_id
        else:
            scope_filter = Tariff.plaza_id == trip.entry_plaza_id

        tariff = (
            self.db.query(Tariff)
            .filter(
                scope_filter,
                Tariff.vehicle_class == vehicle.vehicle_class,
                Tariff.effective_from <= charge_date,
                or_(Tariff.effective_to.is_(None), Tariff.effective_to >= charge_date),
            )
            .order_by(Tariff.effective_from.desc())
            .first()
        )

        if tariff is None:
            scope_desc = f"segment_id={trip.segment_id}" if trip.segment_id else f"plaza_id={trip.entry_plaza_id}"
            raise TariffNotFoundError(
                f"No tariff found for {scope_desc}, vehicle_class={vehicle.vehicle_class}, "
                f"date={charge_date}"
            )

        return tariff

    def _compute_base_amount(self, trip: Trip, tariff: Tariff) -> Decimal:
        if trip.segment_id is None:
            return tariff.base_fare

        distance = trip.distance_travelled_km
        if distance is None:
            # Closed-tolling trip with no recorded distance is itself an
            # anomaly (normally the segment's known distance would have
            # been filled in at trip completion) — fall back to the base
            # fare alone rather than guessing a distance.
            return tariff.base_fare

        rate = tariff.rate_per_km or Decimal("0")
        return tariff.base_fare + (rate * distance)

    def _return_trip_discount(
        self, trip: Trip, vehicle: Vehicle, tariff: Tariff, base_amount: Decimal, charge_time: datetime
    ) -> dict | None:
        if tariff.return_trip_discount_percent <= 0:
            return None

        window_start = charge_time - timedelta(hours=tariff.return_trip_window_hours)

        prior_transaction = (
            self.db.query(Transaction)
            .filter(
                Transaction.vehicle_id == vehicle.vehicle_id,
                Transaction.plaza_id == (trip.entry_plaza_id if trip.segment_id is None else None),
                Transaction.transaction_time >= window_start,
                Transaction.transaction_time < charge_time,
            )
            .first()
        ) if trip.segment_id is None else None

        if prior_transaction is None:
            return None

        amount = (base_amount * tariff.return_trip_discount_percent / Decimal("100")).quantize(Decimal("0.01"))
        return {
            "rule": "return_trip_discount",
            "percent": str(tariff.return_trip_discount_percent),
            "prior_transaction_id": str(prior_transaction.transaction_id),
            "amount": amount,
        }

    def _local_resident_discount(
        self, trip: Trip, vehicle: Vehicle, tariff: Tariff, base_amount: Decimal
    ) -> dict | None:
        if tariff.local_resident_discount_percent <= 0:
            return None

        plaza = self.db.query(Plaza).filter(Plaza.plaza_id == trip.entry_plaza_id).first()
        if plaza is None or vehicle.registration_state != plaza.state_code:
            return None

        amount = (base_amount * tariff.local_resident_discount_percent / Decimal("100")).quantize(Decimal("0.01"))
        return {
            "rule": "local_resident_discount",
            "percent": str(tariff.local_resident_discount_percent),
            "matched_state": plaza.state_code,
            "amount": amount,
        }

    def _night_surcharge(self, tariff: Tariff, base_amount: Decimal, charge_time: datetime) -> dict | None:
        if tariff.night_surcharge_percent <= 0:
            return None

        local_time = charge_time.time()
        is_night = local_time >= NIGHT_START or local_time < NIGHT_END
        if not is_night:
            return None

        amount = (base_amount * tariff.night_surcharge_percent / Decimal("100")).quantize(Decimal("0.01"))
        return {
            "rule": "night_surcharge",
            "percent": str(tariff.night_surcharge_percent),
            "amount": amount,
        }