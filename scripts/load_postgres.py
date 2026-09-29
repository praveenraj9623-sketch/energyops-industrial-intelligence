"""Load the Phase 1-profiled source into the local PostgreSQL raw layer."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.config import DEFAULT_PROFILE, source_path  # noqa: E402
from energyops.database import DatabaseConfig  # noqa: E402
from energyops.ingestion import ingest_csv  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    with DatabaseConfig.from_environment().connect() as conn:
        result = ingest_csv(conn, source_path(args.source), profile["source"]["sha256"], profile["row_count"])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
