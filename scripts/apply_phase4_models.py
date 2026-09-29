"""Create or replace the Phase 4 baseline and eligibility views."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.baseline import apply_baseline_models  # noqa: E402
from energyops.database import DatabaseConfig  # noqa: E402


def main():
    with DatabaseConfig.from_environment().connect() as conn:
        apply_baseline_models(conn)
    print("Applied Phase 4 baseline components, hourly eligibility, and status views.")


if __name__ == "__main__":
    main()
