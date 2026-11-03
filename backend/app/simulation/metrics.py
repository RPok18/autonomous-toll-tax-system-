"""Metrics from the article "04 Simulation: scenarios and metrics".

All rates are percent of passes. Money shares are percent of the expected
toll value of all passes.
"""
from __future__ import annotations

import math
from collections import defaultdict

METHODS = ("anpr_only", "rfid_only", "hybrid_agreed", "hybrid_rfid_primary",
           "hybrid_anpr_primary", "unresolved")
RANGE_KEYS = ("correct_pct", "wrong_pct", "silent_wrong_pct", "unresolved_pct", "exception_pct")


def _pct(part: float, whole: float) -> float:
    return 100.0 * part / whole if whole else 0.0


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100.0 * len(ordered)))
    return ordered[rank - 1]


def summarise(records, scenario_id: str, seed: int) -> dict:
    n = len(records)
    out: dict = {"scenario": scenario_id, "seed": seed, "passes": n}

    correct = sum(r.outcome == "correct" for r in records)
    wrong = sum(r.outcome == "wrong" for r in records)
    unresolved = sum(r.outcome == "unresolved" for r in records)
    exceptions = sum(r.fusion_exception for r in records)
    out["correct_pct"] = _pct(correct, n)
    out["wrong_pct"] = _pct(wrong, n)
    out["silent_wrong_pct"] = _pct(sum(r.silent_wrong for r in records), n)
    out["unresolved_pct"] = _pct(unresolved, n)
    out["exception_pct"] = _pct(exceptions, n)
    out["exceptions_per_1000"] = 10.0 * out["exception_pct"]
    out["unknown_plate_pct"] = _pct(sum(r.charge_status == "no_vehicle" for r in records), n)

    for m in METHODS:
        out[f"method_{m}_pct"] = _pct(sum(r.method == m for r in records), n)

    paid = [r for r in records if r.charge_status == "paid"]
    ok = sum(
        r.charged_to_true_vehicle and r.balance_delta_ok
        and abs(r.charged_amount - r.expected_amount) < 0.005
        for r in paid
    )
    out["toll_deduction_correctness_pct"] = _pct(ok, len(paid))

    expected_total = sum(r.expected_amount for r in records)
    misbilled = sum(r.charged_amount for r in paid if not r.charged_to_true_vehicle)
    missed = sum(r.expected_amount for r in records if r.charge_status != "paid")
    out["misbilled_share_pct"] = _pct(misbilled, expected_total)
    out["missed_revenue_share_pct"] = _pct(missed, expected_total)

    latency = [r.rfid_latency_ms for r in records]
    out["latency_p50_ms"] = percentile(latency, 50)
    out["latency_p95_ms"] = percentile(latency, 95)
    return out


def aggregate(summaries: list[dict]) -> list[dict]:
    """One row per scenario: mean over seeds, plus min and max of the main error metrics."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for s in summaries:
        grouped[s["scenario"]].append(s)

    rows = []
    for scenario_id, items in grouped.items():
        row: dict = {"scenario": scenario_id, "seeds": len(items), "passes": items[0]["passes"]}
        numeric = [k for k, v in items[0].items() if isinstance(v, float)]
        for k in numeric:
            row[k] = sum(i[k] for i in items) / len(items)
        for k in RANGE_KEYS:
            row[f"{k}_min"] = min(i[k] for i in items)
            row[f"{k}_max"] = max(i[k] for i in items)
        rows.append(row)
    return rows


def fusion_gain(rows: list[dict]) -> float | None:
    """Correct rate of S0 minus the better of S1 and S2, in percentage points."""
    by_id = {r["scenario"]: r for r in rows}
    if not all(k in by_id for k in ("S0", "S1", "S2")):
        return None
    return by_id["S0"]["correct_pct"] - max(by_id["S1"]["correct_pct"], by_id["S2"]["correct_pct"])
