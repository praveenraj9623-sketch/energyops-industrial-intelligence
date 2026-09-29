"""Export a small, reproducible, view-backed 2018 public snapshot."""

import csv
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from energyops.database import DatabaseConfig  # noqa: E402

OUT = ROOT / "data" / "export"
VERSION = "energyops_public_snapshot_v1"
QUERIES = {
    "hourly": """SELECT hour_start_local, observed_interval_count, expected_interval_count,
        total_usage_kwh, total_lagging_reactive_power_kvarh,
        mean_lagging_power_factor_pct, light_load_interval_count,
        medium_load_interval_count, maximum_load_interval_count
        FROM analytics.energy_hourly ORDER BY hour_start_local""",
    "daily": """SELECT reading_date, observed_interval_count, expected_interval_count,
        total_usage_kwh, total_lagging_reactive_power_kvarh
        FROM analytics.energy_daily ORDER BY reading_date""",
    "daily_by_load_type": """SELECT reading_date, load_type, observed_interval_count,
        total_usage_kwh, total_lagging_reactive_power_kvarh,
        mean_lagging_power_factor_pct
        FROM analytics.energy_daily_by_load_type ORDER BY reading_date, load_type""",
    "eligibility": """SELECT hour_start_local, eligible, exclusion_reason,
        current_observation_count, expected_observation_count,
        observed_usage_kwh, expected_usage_kwh, excess_kwh, deviation_pct,
        historical_sample_count_min, mean_lagging_power_factor_pct,
        consumption_deviation_candidate, lagging_power_factor_review_candidate,
        combined_priority FROM analytics.energy_rule_evaluation
        ORDER BY hour_start_local""",
    "candidate_hours": """SELECT hour_start_local, observed_usage_kwh, expected_usage_kwh,
        excess_kwh, deviation_pct, mean_lagging_power_factor_pct,
        consumption_deviation_candidate, lagging_power_factor_review_candidate,
        combined_priority FROM analytics.energy_candidate_hours ORDER BY hour_start_local""",
    "incidents": """SELECT incident_key, rule_type, start_hour_local,
        last_candidate_hour_local, observed_hour_count, peak_observed_usage_kwh,
        peak_positive_excess_kwh, peak_signed_deviation_pct,
        minimum_mean_lagging_power_factor_pct, status
        FROM analytics.energy_candidate_incidents ORDER BY start_hour_local, rule_type""",
}


def csv_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def save_table(name, columns, rows):
    target = OUT / f"{name}.csv.gz"
    temp = target.with_suffix(target.suffix + ".tmp")
    with temp.open("wb") as binary:
        with gzip.GzipFile(filename="", fileobj=binary, mode="wb", mtime=0,
                           compresslevel=9) as compressed:
            import io
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(columns)
                for row in rows:
                    writer.writerow([csv_value(value) for value in row])
    os.replace(temp, target)
    return {"file": target.name, "rows": len(rows), "bytes": target.stat().st_size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "columns": columns, "source_view": "analytics.energy_" + name}


def require(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected}, found {actual}")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    evidence = {name: json.loads((ROOT / "evidence" / f"{name}.json").read_text())
                for name in ("phase3_reconciliation", "phase4_baseline_audit",
                             "phase5_rule_audit", "phase6_superset_audit")}
    config = DatabaseConfig.from_environment()
    tables = {}
    with config.connect() as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            for name, query in QUERIES.items():
                cursor = conn.execute(query)
                tables[name] = ([column.name for column in cursor.description], cursor.fetchall())
            source = conn.execute("SELECT min(source_file_sha256), max(source_file_sha256) "
                                  "FROM analytics.energy_hourly").fetchone()
    require(source[0], source[1], "source checksum consistency")
    source_sha = source[0]
    require(source_sha, evidence["phase3_reconciliation"]["csv_sha256"], "Phase 3 source")
    require(source_sha, evidence["phase5_rule_audit"]["source_sha256"], "Phase 5 source")
    require(len(tables["hourly"][1]), 8760, "observed hours")
    require(len(tables["daily"][1]), 365, "observed days")
    require(len(tables["eligibility"][1]), 8760, "eligibility hours")
    require(len(tables["candidate_hours"][1]), 1343, "distinct candidate hours")
    require(len(tables["incidents"][1]), 243, "rule-specific incidents")
    def records(name):
        columns, rows = tables[name]
        return [dict(zip(columns, row)) for row in rows]
    hourly_rows = records("hourly")
    eligibility_rows = records("eligibility")
    incident_rows = records("incidents")
    totals = {
        "observed_hours": len(hourly_rows),
        "observed_intervals": sum(r["observed_interval_count"] for r in hourly_rows),
        "usage_kwh": sum((r["total_usage_kwh"] for r in hourly_rows), Decimal(0)),
        "eligible_hours": sum(r["eligible"] is True for r in eligibility_rows),
        "excluded_hours": sum(r["eligible"] is False for r in eligibility_rows),
        "consumption_positive_hours": sum(r["consumption_deviation_candidate"] is True for r in eligibility_rows),
        "pf_positive_hours": sum(r["lagging_power_factor_review_candidate"] is True for r in eligibility_rows),
        "combined_priority_hours": sum(r["combined_priority"] is True for r in eligibility_rows),
        "distinct_candidate_hours": len(tables["candidate_hours"][1]),
        "consumption_incidents": sum(r["rule_type"] == "consumption_deviation" for r in incident_rows),
        "pf_incidents": sum(r["rule_type"] == "lagging_power_factor_review" for r in incident_rows),
    }
    expected = {"observed_hours": 8760, "observed_intervals": 35040,
                "usage_kwh": Decimal("959636.71"), "eligible_hours": 7762,
                "excluded_hours": 998, "consumption_positive_hours": 1263,
                "pf_positive_hours": 105, "combined_priority_hours": 25,
                "distinct_candidate_hours": 1343, "consumption_incidents": 238,
                "pf_incidents": 5}
    for label, value in expected.items():
        require(totals[label], value, label)
    phase3_hourly = evidence["phase3_reconciliation"]["model_totals"]["energy_hourly"]
    require(totals["observed_intervals"], phase3_hourly["intervals"], "Phase 3 intervals")
    require(str(totals["usage_kwh"]), phase3_hourly["usage_kwh"], "Phase 3 kWh")
    require(str(totals["usage_kwh"]), evidence["phase6_superset_audit"]["raw_usage_kwh"], "Phase 6 kWh")
    require(totals["eligible_hours"], evidence["phase4_baseline_audit"]["eligible_hours"], "Phase 4 eligible")
    require(totals["excluded_hours"], evidence["phase4_baseline_audit"]["excluded_hours"], "Phase 4 excluded")
    require(totals["distinct_candidate_hours"], evidence["phase5_rule_audit"]["candidate_hours_any"], "Phase 5 candidates")
    require(totals["combined_priority_hours"], evidence["phase5_rule_audit"]["combined_priority_hours"], "Phase 5 combined")
    rules = {row["rule_type"]: row for row in evidence["phase5_rule_audit"]["rule_summary"]}
    require(totals["consumption_positive_hours"], rules["consumption_deviation"]["positive_hours"], "Phase 5 consumption hours")
    require(totals["pf_positive_hours"], rules["lagging_power_factor_review"]["positive_hours"], "Phase 5 PF hours")
    require(totals["consumption_incidents"], rules["consumption_deviation"]["sustained_incidents"], "Phase 5 consumption incidents")
    require(totals["pf_incidents"], rules["lagging_power_factor_review"]["sustained_incidents"], "Phase 5 PF incidents")
    require(totals["distinct_candidate_hours"], evidence["phase6_superset_audit"]["candidate_hours"], "Phase 6 candidates")
    files = {name: save_table(name, *tables[name]) for name in QUERIES}
    files["hourly"]["source_view"] = "analytics.energy_hourly"
    files["daily"]["source_view"] = "analytics.energy_daily"
    files["daily_by_load_type"]["source_view"] = "analytics.energy_daily_by_load_type"
    files["eligibility"]["source_view"] = "analytics.energy_rule_evaluation"
    files["candidate_hours"]["source_view"] = "analytics.energy_candidate_hours"
    files["incidents"]["source_view"] = "analytics.energy_candidate_incidents"
    manifest = {"snapshot_version": VERSION,
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "period_start_local": "2018-01-01 00:00:00",
                "period_end_exclusive_local": "2019-01-01 00:00:00",
                "timestamp_timezone": "unspecified facility-local",
                "source_csv_sha256": source_sha,
                "source_readings": 35040,
                "files": files,
                "totals": {key: str(value) if isinstance(value, Decimal) else value
                           for key, value in totals.items()},
                "reconciled_evidence": list(evidence)}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Public snapshot exported: " + ", ".join(f"{name}={meta['rows']}"
                                                   for name, meta in files.items()))
    print(f"Snapshot bytes: {sum(item['bytes'] for item in files.values())}")


if __name__ == "__main__":
    main()
