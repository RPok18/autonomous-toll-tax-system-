# Simulation run results

**Purpose:** Keep measured simulation results next to the code so later changes
can be compared against a dated, reproducible baseline.

**Status:** Baseline demonstration  
**Run date:** 31 October 2026  
**Repository revision:** `2987b53` (`main`); the live-output change is in the
working tree and must be committed before this is used as a release baseline.  
**Environment:** Windows, Python 3.14.7, Docker Desktop available; simulation
uses in-memory synthetic vehicles and does not require PostgreSQL.

## Reproducible live run

From `backend`:

```powershell
python scripts\run_simulation.py --scenario S0,S3,S10 --passes 20 --seeds 42 --live --per-pass --out-dir simulation_results\live_demo
```

`--live` prints one line as each pass is processed. `--per-pass` writes the
same records to CSV. The output is deterministic for the same scenarios,
passes, and seed; the terminal output is observational evidence and the CSV
files are the durable evidence.

The generated evidence is in
[live_demo](../../backend/simulation_results/live_demo/):

- `summary.csv` — one row per scenario and seed.
- `summary_by_scenario.csv` — aggregated scenario rows.
- `metrics_summary.csv` — headline metrics.
- `passes_S0_seed42.csv`, `passes_S3_seed42.csv`, and
  `passes_S10_seed42.csv` — pass-level records.

## Observed scenario counts

Each scenario ran **20 passes**, with **1 seed** (`42`):

| Scenario | Meaning | Passes | Correct identification | Toll-deduction correctness | Latency p50 / p95 | Exception rate |
|---|---|---:|---:|---:|---:|---:|
| S0 | Baseline | 20 | 100.00% | 100.00% | 47.091 / 56.8 ms | 5.00% |
| S3 | Night or rain | 20 | 95.00% | 100.00% | 47.091 / 56.8 ms | 0.00% |
| S10 | Unreadable plates and no tags | 20 | 0.00% | 0.00% | 44.043 / 55.472 ms | 100.00% |

Values above are copied from `metrics_summary.csv`. The exact implementation
columns and units are:

- `correct_identification_pct` — percentage of simulated passes identified
  correctly.
- `toll_deduction_correctness_pct` — percentage of paid passes with the
  correct vehicle and exact simulated deduction.
- `latency_p50_ms` and `latency_p95_ms` — modeled RFID-read latency in
  milliseconds per vehicle pass.
- `exception_pct` — percentage of passes held or routed as an exception.

The rows are per scenario aggregated over one seed; with one seed, the
aggregated values equal that seed's values.

## Unexpected results and next step

S3 produced 5.00% wrong identification and 0.00% exceptions in this small
seeded run. This is a modeled result, not evidence that poor camera visibility
is safe in production. **Decision:** retain it as a regression fixture and
compare it with larger runs before changing policy. **Owner:** ANPR/fusion
maintainer. **Next step:** rerun S3 with the planned multi-seed baseline and
inspect silent misbilling alongside exception rate.

S10 correctly exercised the no-usable-signal path: all 20 passes were
unresolved and exceptions. This confirms the scenario is useful for exception
routing, but it does not validate live camera or OCR behavior.

## Limitations

The simulator uses synthetic ANPR/RFID signals, an in-memory vehicle registry,
and modeled RFID latency. It does not process camera images, invoke Tesseract,
measure detector runtime, or establish production accuracy, revenue, or
security. No secrets or personal data are included in the run or its output.
