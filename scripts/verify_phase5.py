"""Verify Phase 5 rules against source records and independently grouped incidents."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.config import DEFAULT_PROFILE, source_path  # noqa: E402
from energyops.database import DatabaseConfig  # noqa: E402
from energyops.phase5_audit import audit_phase5  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "phase5_rule_audit.json")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    with DatabaseConfig.from_environment().connect() as conn:
        result = audit_phase5(conn, source_path(args.source), profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["audit_status"] != "passed":
        raise SystemExit("Phase 5 audit failed: " + "; ".join(result["problems"][:10]))
    print(f"Phase 5 audit passed: {result['candidate_hours_any']} candidate hours, "
          f"{sum(r['sustained_incidents'] for r in result['rule_summary'])} sustained candidates")


if __name__ == "__main__":
    main()
