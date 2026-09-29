"""Apply rerunnable Phase 2 SQL to the configured local database."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.database import DatabaseConfig, initialize_database  # noqa: E402


def main():
    with DatabaseConfig.from_environment().connect() as conn:
        initialize_database(conn)
    print("Phase 2 schemas, tables, view, and indexes initialized.")


if __name__ == "__main__":
    main()
