"""Report files for the thesis numbers (task B3): the four B1 metrics in one small CSV.

The four metrics come from the article "04 Simulation: scenarios and metrics":
plate accuracy (correct identification rate), toll-deduction correctness,
latency per vehicle and exception rate. ``summary_by_scenario.csv`` keeps every
column; ``metrics_summary.csv`` keeps only these four, with names that can be
pasted into the report.
"""
from __future__ import annotations

from pathlib import Path

from app.simulation.export import write_rows_csv

# Passes written to the per-vehicle CSV automatically; a bigger run needs --per-pass.
PER_PASS_AUTO_LIMIT = 100_000

HEADLINE_COLUMNS = [
    "scenario",
    "seeds",
    "passes",
    "correct_identification_pct",
    "toll_deduction_correctness_pct",
    "latency_p50_ms",
    "latency_p95_ms",
    "exception_pct",
    "exceptions_per_1000",
]

_SOURCE = {
    "correct_identification_pct": "correct_pct",
    "toll_deduction_correctness_pct": "toll_deduction_correctness_pct",
    "latency_p50_ms": "latency_p50_ms",
    "latency_p95_ms": "latency_p95_ms",
    "exception_pct": "exception_pct",
    "exceptions_per_1000": "exceptions_per_1000",
}


def headline_rows(by_scenario: list[dict]) -> list[dict]:
    """One row per scenario with the four metrics; a missing value counts as 0."""
    rows = []
    for item in by_scenario:
        row = {
            "scenario": item["scenario"],
            "seeds": item.get("seeds", 1),
            "passes": item.get("passes", 0),
        }
        for column, source in _SOURCE.items():
            row[column] = item.get(source, 0.0)
        rows.append(row)
    return rows


def write_headline_csv(path: Path | str, by_scenario: list[dict]) -> Path:
    """Write the four-metric summary. With no rows it still writes the header line."""
    return write_rows_csv(path, headline_rows(by_scenario), HEADLINE_COLUMNS)


def want_per_pass(force: bool, disable: bool, total_passes: int) -> bool:
    """Per-vehicle CSV: on for runs up to PER_PASS_AUTO_LIMIT passes, otherwise only when forced."""
    if force and disable:
        raise ValueError("--per-pass and --no-per-pass cannot be used together")
    if disable:
        return False
    return force or total_passes <= PER_PASS_AUTO_LIMIT
