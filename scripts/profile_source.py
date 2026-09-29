"""Generate a compact, reproducible profile of the original CSV."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.config import DEFAULT_PROFILE, source_path  # noqa: E402
from energyops.source_validation import profile_csv  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="CSV path; overrides ENERGYOPS_SOURCE_CSV")
    parser.add_argument("--archive", type=Path, help="Optional original ZIP for checksum")
    parser.add_argument("--output", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    profile = profile_csv(source_path(args.source), args.archive)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Profiled {profile['row_count']:,} rows: {args.output}")


if __name__ == "__main__":
    main()
