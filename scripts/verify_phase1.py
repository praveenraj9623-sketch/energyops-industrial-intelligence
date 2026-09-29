"""Check the Phase 1 source against the saved evidence and contract."""

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
    parser.add_argument("--source", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    args = parser.parse_args()
    saved = json.loads(args.profile.read_text(encoding="utf-8"))
    current = profile_csv(source_path(args.source))
    problems = []
    if current["source"] != saved["source"]:
        problems.append("source identity differs from evidence/source_profile.json")
    if current["row_count"] != 35040:
        problems.append(f"expected 35,040 rows; found {current['row_count']}")
    if current["column_count"] != 11:
        problems.append("expected 11 source columns")
    if current["timestamp"]["parse_failure_count"]:
        problems.append("unparseable timestamps")
    if any(current["missing_values"].values()):
        problems.append("missing values")
    if current["duplicate_complete_rows"] or current["duplicate_timestamps"]:
        problems.append("duplicate rows or timestamps")
    if current["intervals"]["missing_interval_count"] or current["intervals"]["off_grid_timestamp_count"]:
        problems.append("interval gaps or off-grid timestamps")
    if any(current["cross_field_checks"].values()):
        problems.append("date, week status, or NSM disagree")
    if any(values for values in current["unexpected_categories"].values()):
        problems.append("unexpected category values")
    for name, checks in current["numeric_checks"].items():
        if any(value for key, value in checks.items() if key.endswith("_count")):
            problems.append(f"invalid numeric values in {name}")
    if problems:
        raise SystemExit("Phase 1 verification failed:\n- " + "\n- ".join(problems))
    print("Phase 1 verification passed: source checksum, schema, 35,040 rows, continuity, and validation checks.")


if __name__ == "__main__":
    main()
