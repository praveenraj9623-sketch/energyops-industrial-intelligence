"""Audit Phase 4 baseline windows and eligibility against independent CSV records."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.baseline_audit import audit_phase4  # noqa: E402
from energyops.config import DEFAULT_PROFILE, source_path  # noqa: E402
from energyops.database import DatabaseConfig  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "phase4_baseline_audit.json")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    with DatabaseConfig.from_environment().connect() as conn:
        result = audit_phase4(conn, source_path(args.source), profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if result["audit_status"] != "passed":
        raise SystemExit("Phase 4 audit failed: " + "; ".join(result["problems"][:10]))
    print(f"Phase 4 audit passed: {result['eligible_hours']:,} eligible, "
          f"{result['excluded_hours']:,} excluded hours; evidence: {args.output}")


if __name__ == "__main__":
    main()
