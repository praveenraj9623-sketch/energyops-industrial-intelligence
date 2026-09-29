"""Create or replace Phase 3 analytics views in dependency order."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.analytics import MODEL_NAMES, apply_analytics_models  # noqa: E402
from energyops.database import DatabaseConfig  # noqa: E402


def main():
    with DatabaseConfig.from_environment().connect() as conn:
        apply_analytics_models(conn)
    print("Applied Phase 3 analytics views: " + ", ".join(MODEL_NAMES))


if __name__ == "__main__":
    main()
