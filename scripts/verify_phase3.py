"""Compare Phase 3 PostgreSQL views to independent source CSV aggregations."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.config import DEFAULT_PROFILE, source_path  # noqa: E402
from energyops.database import DatabaseConfig  # noqa: E402
from energyops.phase3_reconciliation import reconcile_phase3  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "phase3_reconciliation.json")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    with DatabaseConfig.from_environment().connect() as conn:
        result = reconcile_phase3(conn, source_path(args.source), profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if result["reconciliation_status"] != "passed":
        raise SystemExit("Phase 3 reconciliation failed: " + "; ".join(result["problems"][:10]))
    print(f"Phase 3 reconciliation passed: {result['model_row_counts']['energy_hourly']:,} hours, "
          f"{result['model_row_counts']['energy_daily']:,} days; evidence: {args.output}")


if __name__ == "__main__":
    main()
