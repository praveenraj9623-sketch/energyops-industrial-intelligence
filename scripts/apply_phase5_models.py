"""Create or replace the Phase 5 candidate investigation views."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.database import DatabaseConfig  # noqa: E402
from energyops.investigation_rules import apply_investigation_models  # noqa: E402


def main():
    with DatabaseConfig.from_environment().connect() as conn:
        apply_investigation_models(conn)
    print("Applied Phase 5 rule evaluation, candidate hours, incidents and summary views.")


if __name__ == "__main__":
    main()
