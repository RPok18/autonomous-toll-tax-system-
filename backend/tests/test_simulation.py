"""Tests for the simulation harness (tasks B2 and B3).

The four "case" tests mirror the per-vehicle cases in the article
"04 Simulation: scenarios and metrics".
"""
from __future__ import annotations

import csv
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.anpr.reader import ANPRSignal
from app.config import Settings
from app.fusion.fusion_engine import FusionEngine
from app.models.enums import VehicleClass
from app.policy.rules_engine import PolicyEngine, TollContext
from app.rfid.simulator import RFIDReadResult
from app.simulation.export import PASS_COLUMNS, write_pass_csv, write_rows_csv
from app.simulation.metrics import aggregate, fusion_gain, summarise
from app.simulation.runner import Registry, SimVehicle, process_pass, run_scenario
from app.simulation.scenarios import SCENARIOS, Scenario, get_scenarios, threshold_sweep

CAR_TOLL = Decimal("65.00")  # plaza-01 base rate for car_jeep_van


def engine(primary="rfid", mode="hybrid", anpr_min=0.55, rfid_min=0.5):
    return FusionEngine(settings=SimpleNamespace(
        anpr_min_confidence=anpr_min, rfid_min_confidence=rfid_min,
        fusion_primary_signal=primary, fusion_mode=mode))


def registry(*vehicles):
    return Registry(list(vehicles))


def car(plate, balance="100.00", tag=None):
    return SimVehicle(plate, tag or f"TAG{plate}", VehicleClass.CAR_JEEP_VAN, Decimal(balance))


NO_TAG = RFIDReadResult(tag_id=None, confidence=0.0, read_latency_ms=45.0, tag_registered=False)
CTX = TollContext(timestamp=datetime(2026, 10, 1, 12))


def run_pass(eng, reg, vehicle, anpr, rfid=NO_TAG, carried=None):
    return process_pass(engine=eng, policy=PolicyEngine(), registry=reg,
                        true_vehicle=vehicle, anpr=anpr, rfid=rfid,
                        carried_tag=carried, context=CTX)


# ---- the four per-vehicle cases -------------------------------------------

def test_case_1_clean_plate_is_charged_the_exact_toll():
    v = car("MH12AB1234")
    rec = run_pass(engine(), registry(v), v, ANPRSignal("MH12AB1234", 0.93))
    assert rec.method == "anpr_only"
    assert not rec.fusion_exception
    assert rec.charge_status == "paid"
    assert rec.charged_amount == float(CAR_TOLL)
    assert v.balance == Decimal("100.00") - CAR_TOLL  # 100.00 -> 35.00


def test_case_1_with_an_agreeing_tag_is_hybrid_agreed():
    v = car("MH12AB1234")
    tag = RFIDReadResult(v.tag_id, 0.95, 45.0, True)
    rec = run_pass(engine(), registry(v), v, ANPRSignal("MH12AB1234", 0.93), tag, v.tag_id)
    assert rec.method == "hybrid_agreed"
    assert rec.charge_status == "paid"


@pytest.mark.parametrize("anpr", [ANPRSignal(None, 0.0), ANPRSignal("MH12AB1234", 0.30)])
def test_case_2_blurred_plate_is_unresolved_and_not_charged(anpr):
    v = car("MH12AB1234")
    rec = run_pass(engine(), registry(v), v, anpr)
    assert rec.method == "unresolved"
    assert rec.fusion_exception
    assert rec.charge_status == "unresolved"
    assert v.balance == Decimal("100.00")


def test_case_2_blurred_plate_with_a_readable_tag_becomes_rfid_only():
    v = car("MH12AB1234")
    tag = RFIDReadResult(v.tag_id, 0.95, 45.0, True)
    rec = run_pass(engine(), registry(v), v, ANPRSignal(None, 0.0), tag, v.tag_id)
    assert rec.method == "rfid_only"
    assert rec.charge_status == "paid"
    assert v.balance == Decimal("100.00") - CAR_TOLL


def test_case_3_wrong_plate_not_registered_means_no_vehicle_and_no_charge():
    v = car("MH12AB1000")
    rec = run_pass(engine(), registry(v), v, ANPRSignal("MH12ABI000", 0.60))  # 1 -> I
    assert rec.outcome == "wrong"
    assert rec.charge_status == "no_vehicle"
    assert v.balance == Decimal("100.00")


def test_case_3_wrong_plate_matching_another_vehicle_is_a_silent_misbilling():
    true_v, other = car("MH12AB1000"), car("MH12AB1001")
    rec = run_pass(engine(), registry(true_v, other), true_v, ANPRSignal("MH12AB1001", 0.60))
    assert rec.outcome == "wrong" and rec.silent_wrong
    assert rec.charge_status == "paid" and not rec.charged_to_true_vehicle
    assert other.balance == Decimal("100.00") - CAR_TOLL
    assert true_v.balance == Decimal("100.00")


@pytest.mark.parametrize("primary", ["rfid", "anpr"])
def test_case_3_disagreeing_tag_raises_an_exception_and_holds_the_pass(primary):
    # The vehicle (MH12AB1000) carries a tag registered to MH12AB1001.
    true_v, other = car("MH12AB1000"), car("MH12AB1001")
    rfid = RFIDReadResult(other.tag_id, 0.95, 45.0, True)
    rec = run_pass(engine(primary=primary), registry(true_v, other), true_v,
                   ANPRSignal("MH12AB1000", 0.93), rfid, other.tag_id)
    assert rec.fusion_exception
    assert "anpr_rfid_conflict" in rec.notes
    assert rec.charge_status == "held_exception"
    assert true_v.balance == other.balance == Decimal("100.00")
    # RFID primary resolves to the tag owner (wrong), ANPR primary to the true plate
    assert rec.resolved_plate == (other.plate if primary == "rfid" else true_v.plate)


def test_case_4_insufficient_balance_is_refused_and_balance_is_unchanged():
    v = car("MH12AB1234", balance="10.00")
    rec = run_pass(engine(), registry(v), v, ANPRSignal("MH12AB1234", 0.93))
    assert rec.outcome == "correct"
    assert rec.charge_status == "insufficient_balance"
    assert rec.charged_amount == 0.0
    assert v.balance == Decimal("10.00")


# ---- fusion settings ------------------------------------------------------

def test_settings_define_the_fusion_fields():
    s = Settings()
    assert s.rfid_min_confidence == 0.5
    assert s.fusion_primary_signal in ("rfid", "anpr")


def test_fusion_engine_resolves_a_registered_tag_without_attribute_error():
    # Regression: this raised AttributeError before the settings were added.
    v = car("MH12AB1234")
    tag = RFIDReadResult(v.tag_id, 0.95, 45.0, True)
    result = FusionEngine(settings=Settings()).resolve(ANPRSignal("MH12AB1234", 0.93), tag, v.plate)
    assert result.identification_method.value == "hybrid_agreed"


def test_fusion_mode_switches_one_signal_off():
    v = car("MH12AB1234")
    tag = RFIDReadResult(v.tag_id, 0.95, 45.0, True)
    anpr = ANPRSignal("MH12AB1234", 0.93)
    assert engine(mode="anpr_only").resolve(anpr, tag, v.plate).identification_method.value == "anpr_only"
    assert engine(mode="rfid_only").resolve(anpr, tag, v.plate).identification_method.value == "rfid_only"


# ---- runner and metrics ---------------------------------------------------

def _strip_timing(records):
    return [{k: v for k, v in r.__dict__.items() if k != "decision_ms"} for r in records]


def test_same_seed_gives_identical_results():
    a = run_scenario(SCENARIOS["S3"], seed=3, passes=400)
    b = run_scenario(SCENARIOS["S3"], seed=3, passes=400)
    assert _strip_timing(a) == _strip_timing(b)


def test_different_seeds_give_different_results():
    a = run_scenario(SCENARIOS["S3"], seed=1, passes=400)
    b = run_scenario(SCENARIOS["S3"], seed=2, passes=400)
    assert _strip_timing(a) != _strip_timing(b)


def test_outcome_rates_add_up_to_100_percent():
    s = summarise(run_scenario(SCENARIOS["S6"], seed=1, passes=1000), "S6", 1)
    assert s["correct_pct"] + s["wrong_pct"] + s["unresolved_pct"] == pytest.approx(100.0)


def test_anpr_outage_cannot_identify_a_vehicle_wrongly_without_a_cloned_tag():
    s = summarise(run_scenario(SCENARIOS["S2"], seed=1, passes=2000), "S2", 1)
    assert s["silent_wrong_pct"] < 0.5          # only rare garbled-tag collisions
    assert s["unresolved_pct"] > 15


def test_baseline_is_in_the_expected_range():
    s = summarise(run_scenario(SCENARIOS["S0"], seed=1, passes=4000), "S0", 1)
    assert 96.0 < s["correct_pct"] < 99.5
    assert s["toll_deduction_correctness_pct"] > 99.0


def test_hybrid_beats_each_single_signal():
    rows = []
    for sid in ("S0", "S1", "S2"):
        rows.append(summarise(run_scenario(SCENARIOS[sid], seed=1, passes=2000), sid, 1))
    assert fusion_gain(aggregate(rows)) > 0


def test_fusion_gain_is_none_without_s0_s1_s2():
    rows = aggregate([summarise(run_scenario(SCENARIOS["S0"], 1, 50), "S0", 1)])
    assert fusion_gain(rows) is None


def test_low_balance_vehicles_are_refused_not_charged():
    sc = Scenario(scenario_id="T", name="t", description="", low_balance_share=1.0)
    records = run_scenario(sc, seed=1, passes=300)
    # exempt two-wheelers have a toll of 0, so a zero balance still covers them
    assert not any(r.charge_status == "paid" and r.charged_amount > 0 for r in records)
    assert any(r.charge_status == "insufficient_balance" for r in records)


# ---- scenarios ------------------------------------------------------------

def test_unknown_scenario_is_rejected_with_the_known_ids():
    with pytest.raises(ValueError, match="Unknown scenario 'S42'"):
        get_scenarios("S42")


def test_all_selector_includes_the_threshold_sweep():
    ids = [s.scenario_id for s in get_scenarios("all")]
    assert "S0" in ids and "S8b" in ids
    assert len(threshold_sweep()) == 14 and "S9-S3-t0.85" in ids


def test_negative_passes_are_rejected():
    with pytest.raises(ValueError):
        run_scenario(SCENARIOS["S0"], seed=1, passes=-1)


# ---- export (B3) ----------------------------------------------------------

def test_empty_run_writes_headers_and_a_zero_summary(tmp_path):
    records = run_scenario(SCENARIOS["S0"], seed=1, passes=0)
    assert records == []
    pass_csv = write_pass_csv(tmp_path / "passes.csv", records)
    summary = summarise(records, "S0", 1)
    summary_csv = write_rows_csv(tmp_path / "summary.csv", [summary])
    with pass_csv.open(newline="") as fh:
        rows = list(csv.reader(fh))
    assert rows == [PASS_COLUMNS]
    with summary_csv.open(newline="") as fh:
        row = next(csv.DictReader(fh))
    assert row["passes"] == "0" and float(row["correct_pct"]) == 0.0


def test_pass_csv_has_one_row_per_pass(tmp_path):
    records = run_scenario(SCENARIOS["S0"], seed=1, passes=25)
    path = write_pass_csv(tmp_path / "p.csv", records)
    with path.open(newline="") as fh:
        assert len(list(csv.DictReader(fh))) == 25
