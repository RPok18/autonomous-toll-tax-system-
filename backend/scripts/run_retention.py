"""Apply the data-retention rules (decision record 07).

Run from the backend folder, for example once a day:

    python scripts/run_retention.py --dry-run     # show what would be removed
    python scripts/run_retention.py               # remove it

Periods come from settings (anpr_image_retention_days, record_retention_days);
the options below override them for one run.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.retention import purge_expired  # noqa: E402
from app.database import SessionLocal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="count what would be removed, change nothing")
    parser.add_argument("--image-days", type=int, help="days a plate image is kept after its exception is resolved")
    parser.add_argument("--record-days", type=int, help="days transactions, exceptions and audit entries are kept")
    args = parser.parse_args()

    with SessionLocal() as db:
        report = purge_expired(db, image_days=args.image_days, record_days=args.record_days, dry_run=args.dry_run)

    print("DRY RUN, nothing was changed" if report.dry_run else "Retention run finished")
    for name, value in report.as_dict().items():
        if name != "dry_run":
            print(f"  {name}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
