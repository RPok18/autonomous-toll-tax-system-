"""Tests for the simulation export files (task B3): per-vehicle CSV and the four-metric summary."""
from __future__ import annotations

import csv
import importlib.util
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from app.simulation.export import PASS_COLUMNS
from app.simulation.report import (
    HEADLINE_COLUMNS,
    PER_PASS_AUTO_LIMIT,
    headline_rows,
    want_per_pass,
    write_headline_csv,
)


def load_script():
    spec = importlib.util.spec_from_file_location("run_simulation_script", BACKEND / "scripts" / "run_simulation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def header(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as fh:
        return next(csv.reader(fh))


def run_cli(tmp_path, *args) -> int:
    return load_script().main([*args, "--out-dir", str(tmp_path)])


# ---------------------------------------------------------------- the empty run

def test_empty_run_writes_headers_and_a_zero_summary_without_error(tmp_path, capsys):
    code = run_cli(tmp_path, "--scenario", "S0", "--passes", "0", "--seeds", "1")

    assert code == 0
    assert header(tmp_path / "passes_S0_seed1.csv") == PASS_COLUMNS
    assert read(tmp_path / "passes_S0_seed1.csv") == []  # headers only, no vehicle rows
    assert header(tmp_path / "metrics_summary.csv") == HEADLINE_COLUMNS
    (row,) = read(tmp_path / "metrics_summary.csv")
    assert row["scenario"] == "S0" and row["passes"] == "0"
    for column in HEADLINE_COLUMNS[3:]:
        assert float(row[column]) == 0.0, column
    assert "Traceback" not in capsys.readouterr().err


def test_empty_summary_input_still_writes_the_header(tmp_path):
    path = write_headline_csv(tmp_path / "m.csv", [])

    assert header(path) == HEADLINE_COLUMNS
    assert read(path) == []


# ---------------------------------------------------------------- a normal run

def test_run_writes_one_row_per_vehicle_and_the_four_metrics(tmp_path):
    assert run_cli(tmp_path, "--scenario", "S0", "--passes", "200", "--seeds", "1,2") == 0

    for seed in (1, 2):
        assert len(read(tmp_path / f"passes_S0_seed{seed}.csv")) == 200
    (row,) = read(tmp_path / "metrics_summary.csv")
    assert row["seeds"] == "2" and row["passes"] == "200"
    assert 0 < float(row["correct_identification_pct"]) <= 100
    assert float(row["latency_p95_ms"]) >= float(row["latency_p50_ms"]) >= 0
    assert float(row["exceptions_per_1000"]) == pytest.approx(10 * float(row["exception_pct"]), abs=0.01)


def test_headline_numbers_equal_the_full_summary(tmp_path):
    run_cli(tmp_path, "--scenario", "S0,S1", "--passes", "300", "--seeds", "1-2", "--no-per-pass")

    full = {r["scenario"]: r for r in read(tmp_path / "summary_by_scenario.csv")}
    short = read(tmp_path / "metrics_summary.csv")
    assert [r["scenario"] for r in short] == ["S0", "S1"]
    for r in short:
        assert float(r["correct_identification_pct"]) == pytest.approx(float(full[r["scenario"]]["correct_pct"]), abs=1e-3)
        assert float(r["toll_deduction_correctness_pct"]) == pytest.approx(
            float(full[r["scenario"]]["toll_deduction_correctness_pct"]), abs=1e-3)
        assert float(r["latency_p95_ms"]) == pytest.approx(float(full[r["scenario"]]["latency_p95_ms"]), abs=1e-3)


def test_headline_rows_use_zero_for_missing_values():
    (row,) = headline_rows([{"scenario": "X"}])

    assert row["passes"] == 0 and row["correct_identification_pct"] == 0.0 and row["latency_p95_ms"] == 0.0


# ---------------------------------------------------------------- per-vehicle file switch

def test_no_per_pass_flag_skips_the_vehicle_files(tmp_path):
    assert run_cli(tmp_path, "--scenario", "S0", "--passes", "20", "--seeds", "1", "--no-per-pass") == 0

    assert not list(tmp_path.glob("passes_*.csv"))
    assert (tmp_path / "metrics_summary.csv").exists()


def test_both_per_pass_flags_together_are_a_usage_error(tmp_path, capsys):
    assert run_cli(tmp_path, "--passes", "5", "--per-pass", "--no-per-pass") == 2
    assert "cannot be used together" in capsys.readouterr().err


def test_large_runs_skip_the_vehicle_files_unless_forced():
    assert want_per_pass(False, False, PER_PASS_AUTO_LIMIT) is True
    assert want_per_pass(False, False, PER_PASS_AUTO_LIMIT + 1) is False
    assert want_per_pass(True, False, PER_PASS_AUTO_LIMIT + 1) is True
    assert want_per_pass(False, True, 10) is False
