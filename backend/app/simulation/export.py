"""CSV export for simulation results (task B3). An empty run still writes headers."""
from __future__ import annotations

import csv
from dataclasses import asdict, fields
from pathlib import Path

from app.simulation.runner import PassRecord

PASS_COLUMNS = [f.name for f in fields(PassRecord)]


def write_pass_csv(path: Path | str, records) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=PASS_COLUMNS)
        writer.writeheader()
        for r in records:
            writer.writerow(asdict(r))
    return path


def write_rows_csv(path: Path | str, rows: list[dict], columns: list[str] | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = columns or (list(rows[0].keys()) if rows else ["scenario", "seed", "passes"])
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()})
    return path
