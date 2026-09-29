"""Verify committed public files without Docker, PostgreSQL or secrets."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from energyops.public_snapshot import load_snapshot, period_metrics  # noqa: E402


def main():
    manifest, tables = load_snapshot(ROOT / "data" / "export")
    actual = period_metrics(tables["hourly"], tables["eligibility"],
                            tables["candidate_hours"], tables["incidents"])
    expected = manifest["totals"]
    manifest_names = {"intervals": "observed_intervals",
                      "candidate_hours": "distinct_candidate_hours"}
    for key, value in actual.items():
        expected_value = expected[manifest_names.get(key, key)]
        if key == "usage_kwh":
            if abs(value - float(expected_value)) > 0.000001:
                raise AssertionError("Snapshot energy does not match manifest")
        elif value != expected_value:
            raise AssertionError(f"Snapshot metric mismatch: {key}")
    daily = tables["daily"]
    load = tables["daily_by_load_type"]
    if abs(daily["total_usage_kwh"].sum() - actual["usage_kwh"]) > 0.000001:
        raise AssertionError("Daily energy does not reconcile to hourly")
    if abs(load["total_usage_kwh"].sum() - actual["usage_kwh"]) > 0.000001:
        raise AssertionError("Load-class energy does not reconcile to hourly")
    phase6 = json.loads((ROOT / "evidence" / "phase6_superset_audit.json").read_text())
    if actual["observed_hours"] != phase6["eligibility"][0] + phase6["eligibility"][1]:
        raise AssertionError("Observed-hour evidence mismatch")
    if actual["candidate_hours"] != phase6["candidate_hours"]:
        raise AssertionError("Candidate-hour evidence mismatch")
    print(f"Public snapshot verified offline: {len(tables)} tables, "
          f"{sum(info['bytes'] for info in manifest['files'].values())} compressed bytes")


if __name__ == "__main__":
    main()
