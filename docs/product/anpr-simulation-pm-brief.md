# PM brief: ANPR and RFID toll simulation

## Summary

The simulation runner lets the team compare how automatic number-plate
recognition (ANPR) and RFID work together to identify a vehicle and determine
whether a toll should be charged. It exercises normal operation and modeled
failure conditions without requiring live cameras, roadside hardware, or
production transactions.

The goal is to make trade-offs visible early: a wrong vehicle association can
misbill a customer, while an unreadable pass can delay revenue and require
manual review. The simulation records both identification and toll-ledger
outcomes so the team can compare scenarios consistently.

## What it covers

- A baseline scenario and scenarios for ANPR or RFID outages, poor camera
  visibility, degraded RFID reads, fewer tagged vehicles, and cloned tags.
- Configurable conflict handling when ANPR and RFID disagree.
- A confidence-threshold sweep under baseline and poor-visibility conditions.
- Reproducible runs across configurable random seeds and vehicle-pass counts.
- Summary measures for correct, wrong, silent-wrong, unresolved, and
  exception outcomes; toll deduction correctness; misbilled and missed
  revenue shares; and modeled RFID-read p50/p95 latency.
- Optional per-pass CSV and console output to inspect each vehicle result.

Disagreement exceptions are held rather than charged in the simulated ledger.
The output also distinguishes a payment to the true vehicle from a payment
made to another registered vehicle.

## How to run it

From the `backend` directory:

```text
python scripts/run_simulation.py --list
python scripts/run_simulation.py --scenario all --passes 10000 --seeds 1-5
python scripts/run_simulation.py --scenario all --passes 100 --seeds 42 --per-pass
python scripts/run_simulation.py --scenario S3 --seeds 1 --per-pass
```

The default output directory is `simulation_results`. Each run writes
`summary.csv` and `summary_by_scenario.csv`; it also writes `fusion_gain.csv`
when the baseline and both single-signal comparison scenarios are included.
With `--per-pass`, it writes one pass-level CSV per scenario and seed and
prints a deterministic result line for every vehicle pass. S10 deliberately
combines unreadable ANPR with no available RFID tag to exercise exception
routing. The console output and simulation results are reproducible for a
fixed seed; wall-clock processing time is not included in the modeled latency.

## How to interpret the results

Use results to compare modeled scenarios and identify which failure modes
deserve real-world testing. In particular, review silent misbilling and
missed-revenue rates alongside the exception rate; a higher correct-read rate
alone does not describe customer or revenue impact.

The simulation uses synthetic ANPR and RFID signals and an in-memory vehicle
registry. It does not process real images, measure a camera or detector's
runtime, or establish a production accuracy or revenue forecast. S4's 0.81
ANPR detection rate is a proxy based on a YOLO detector recall measurement
from a small validation set; it is not end-to-end OCR accuracy. Reported
latency is modeled RFID-read latency, not roadside hardware or local
simulation processing time.

## CV experiment evidence

The current YOLOv8n plate-detector run was trained for 80 epochs at 640-pixel
image size. On the 18-image validation split, epoch 80 reported precision
0.875, recall 0.806, mAP@0.5 0.794, and mAP@0.5:0.95 0.444. The best
mAP@0.5:0.95 during training was 0.478 at epoch 50. These are plate-box
detection metrics, not character-recognition or complete tolling accuracy.
The validation set is too small to establish production readiness, so the
result supports continued evaluation of YOLO rather than a claim that live
ANPR is validated.

## PM-facing outcome

This tool is a repeatable engineering decision aid, not a customer-facing
feature or a deployment readiness certification. Its outputs help the team
decide which ANPR/RFID configurations and failure cases to validate with
labelled camera footage and pilot hardware before rollout. The CV experiment
similarly gives the team an initial detector benchmark and a clear next step:
validate on a larger, representative image set and measure full-pipeline
plate-reading accuracy before choosing a production default.

## Related implementation and decisions

- [Simulation CLI](../../backend/scripts/run_simulation.py)
- [Scenario definitions](../../backend/app/simulation/scenarios.py)
- [Simulation metrics](../../backend/app/simulation/metrics.py)
- [Plate detection decision](../decisions/ADR-001-plate-detection.md)
- [OCR decision](../decisions/ADR-002-plate-ocr.md)
- [ANPR threshold decision](../decisions/ADR-003-anpr-confidence-threshold.md)
