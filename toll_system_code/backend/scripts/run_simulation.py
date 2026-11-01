"""Run simulation scenarios and write the metrics (tasks B2 and B3).

Examples (from the backend folder):
    python scripts/run_simulation.py --list
    python scripts/run_simulation.py --scenario S0 --passes 10000 --seeds 1-5
    python scripts/run_simulation.py --scenario all --out-dir simulation_results
    python scripts/run_simulation.py --scenario S3 --seeds 1 --no-per-pass
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.simulation.export import write_pass_csv, write_rows_csv  # noqa: E402
from app.simulation.metrics import aggregate, fusion_gain, summarise  # noqa: E402
from app.simulation.report import PER_PASS_AUTO_LIMIT, want_per_pass, write_headline_csv  # noqa: E402
from app.simulation.runner import run_scenario  # noqa: E402
from app.simulation.scenarios import SCENARIOS, get_scenarios, threshold_sweep  # noqa: E402


def parse_seeds(text: str) -> list[int]:
    seeds: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            seeds.extend(range(int(lo), int(hi) + 1))
        elif part:
            seeds.append(int(part))
    if not seeds:
        raise ValueError("No seeds given")
    return seeds


def print_table(rows: list[dict]) -> None:
    header = f"{'scenario':<16}{'correct':>9}{'wrong':>8}{'silent':>8}{'unres.':>8}{'exc.':>8}{'p95 ms':>9}"
    print(header)
    print("-" * len(header))
    for r in rows:
        print(f"{r['scenario']:<16}{r['correct_pct']:>9.2f}{r['wrong_pct']:>8.2f}"
              f"{r['silent_wrong_pct']:>8.2f}{r['unresolved_pct']:>8.2f}"
              f"{r['exception_pct']:>8.2f}{r['latency_p95_ms']:>9.1f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run toll simulation scenarios")
    ap.add_argument("--scenario", default="S0", help='"all", "S9", or comma-separated ids (default S0)')
    ap.add_argument("--passes", type=int, default=10000, help="passes per scenario and seed")
    ap.add_argument("--seeds", default="1-5", help='e.g. "1-5" or "1,3,7"')
    ap.add_argument("--out-dir", default="simulation_results")
    ap.add_argument("--per-pass", action="store_true",
                    help=f"always write one CSV row per pass (default: only up to {PER_PASS_AUTO_LIMIT} passes in total)")
    ap.add_argument("--no-per-pass", action="store_true", help="never write the per-pass CSV files")
    ap.add_argument("--list", action="store_true", help="list scenarios and exit")
    args = ap.parse_args(argv)

    if args.list:
        for s in list(SCENARIOS.values()) + threshold_sweep()[:1]:
            print(f"{s.scenario_id:<6} {s.name:<28} {s.description}")
        print("S9     Threshold sweep              S0 and S3 with anpr_min_confidence 0.55 to 0.85")
        return 0

    try:
        scenarios = get_scenarios(args.scenario)
        seeds = parse_seeds(args.seeds)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.passes < 0:
        print("error: --passes must not be negative", file=sys.stderr)
        return 2

    try:
        per_pass = want_per_pass(args.per_pass, args.no_per_pass, len(scenarios) * len(seeds) * args.passes)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    summaries: list[dict] = []
    for sc in scenarios:
        for seed in seeds:
            records = run_scenario(sc, seed, args.passes)
            summaries.append(summarise(records, sc.scenario_id, seed))
            if per_pass:
                write_pass_csv(out_dir / f"passes_{sc.scenario_id}_seed{seed}.csv", records)

    by_scenario = aggregate(summaries)
    write_rows_csv(out_dir / "summary.csv", summaries)
    write_rows_csv(out_dir / "summary_by_scenario.csv", by_scenario)
    write_headline_csv(out_dir / "metrics_summary.csv", by_scenario)
    gain = fusion_gain(by_scenario)
    if gain is not None:
        write_rows_csv(out_dir / "fusion_gain.csv", [{"fusion_gain_points": gain}])

    print_table(by_scenario)
    if gain is not None:
        print(f"\nFusion gain (S0 minus the better of S1 and S2): {gain:.2f} points")
    if not per_pass:
        print("\nPer-pass CSV files not written (run is large or --no-per-pass); use --per-pass to force them.")
    print(f"\nWrote results to {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
