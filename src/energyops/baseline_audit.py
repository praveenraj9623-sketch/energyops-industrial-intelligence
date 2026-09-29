"""Independent source-record checks for Phase 4 baselines and eligibility."""

import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from psycopg import sql

from .baseline import METHOD_VERSION, MIN_COMPARABLE_SAMPLES, TRAILING_DAYS, apply_baseline_models
from .provenance import sha256_file
from .source_validation import TIMESTAMP_FORMAT, validate_columns

TOLERANCE = Decimal("0.000001")


@dataclass(frozen=True)
class Reading:
    timestamp: datetime
    usage_kwh: Decimal | None
    load_type: str
    week_status: str


def read_source(path: str | Path) -> list[Reading]:
    readings = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        validate_columns(reader.fieldnames)
        for row in reader:
            readings.append(Reading(datetime.strptime(row["date"], TIMESTAMP_FORMAT),
                                    Decimal(row["Usage_kWh"]), row["Load_Type"], row["WeekStatus"]))
    return readings


def discrete_percentile(values: list[Decimal], fraction: Decimal) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def classify_eligibility(current_count: int, expected_count: int, all_components_supported: bool,
                         other_data_problem: bool = False) -> tuple[bool, str | None, list[str]]:
    current_problem = current_count != expected_count
    baseline_problem = not all_components_supported
    secondary = (["insufficient_current_coverage"] if current_problem else [])
    secondary += (["insufficient_baseline_support"] if baseline_problem else [])
    secondary += (["other_data_problem"] if other_data_problem else [])
    if other_data_problem:
        return False, "other_data_problem", secondary
    if current_problem and baseline_problem:
        return False, "insufficient_current_and_baseline", secondary
    if current_problem:
        return False, "insufficient_current_coverage", secondary
    if baseline_problem:
        return False, "insufficient_baseline_support", secondary
    return True, None, secondary


def evaluate_source_hour(readings: list[Reading], hour_start: datetime) -> dict:
    """Calculate a sampled hour from CSV records, never reading the SQL baseline."""
    end = hour_start
    start = end - timedelta(days=TRAILING_DAYS)
    current = [r for r in readings if r.timestamp.replace(minute=0, second=0, microsecond=0) == hour_start]
    by_load = defaultdict(list)
    for row in current:
        by_load[row.load_type].append(row)
    components = {}
    expected = Decimal(0)
    p10_sum = Decimal(0)
    p90_sum = Decimal(0)
    data_problem = not current or any(row.usage_kwh is None for row in current)
    for load_type, current_rows in sorted(by_load.items()):
        statuses = {row.week_status for row in current_rows}
        if len(statuses) != 1:
            data_problem = True
        status = current_rows[0].week_status
        history = [r for r in readings if start <= r.timestamp < end
                   and r.timestamp.hour == hour_start.hour and r.week_status == status
                   and r.load_type == load_type]
        if any(r.usage_kwh is None for r in history):
            data_problem = True
        values = [r.usage_kwh for r in history if r.usage_kwh is not None]
        p10 = discrete_percentile(values, Decimal("0.10"))
        median = discrete_percentile(values, Decimal("0.50"))
        p90 = discrete_percentile(values, Decimal("0.90"))
        supported = len(history) >= MIN_COMPARABLE_SAMPLES and median is not None and not data_problem
        if supported:
            expected += len(current_rows) * median
            p10_sum += len(current_rows) * p10
            p90_sum += len(current_rows) * p90
        timestamps = [r.timestamp for r in history]
        components[load_type] = {
            "current_interval_count": len(current_rows),
            "historical_sample_count": len(history),
            "historical_first_timestamp_local": min(timestamps).isoformat() if timestamps else None,
            "historical_last_timestamp_local": max(timestamps).isoformat() if timestamps else None,
            "median_15min_usage_kwh": median,
            "p10_15min_usage_kwh": p10,
            "p90_15min_usage_kwh": p90,
            "supported": supported,
            "every_historical_timestamp_before_hour": all(timestamp < hour_start for timestamp in timestamps),
            "every_historical_timestamp_in_window": all(start <= timestamp < end for timestamp in timestamps),
        }
    all_supported = bool(components) and all(c["supported"] for c in components.values())
    eligible, reason, secondary = classify_eligibility(len(current), 4, all_supported, data_problem)
    return {
        "hour_start_local": hour_start,
        "current_observation_count": len(current),
        "observed_usage_kwh": sum((r.usage_kwh for r in current if r.usage_kwh is not None), Decimal(0)),
        "historical_window_start_local": start,
        "historical_window_end_exclusive_local": end,
        "historical_sample_count_total": sum(c["historical_sample_count"] for c in components.values()),
        "historical_sample_count_min": min((c["historical_sample_count"] for c in components.values()), default=None),
        "components": components,
        "expected_usage_kwh": expected if eligible else None,
        "component_p10_sum_kwh": p10_sum if eligible else None,
        "component_p90_sum_kwh": p90_sum if eligible else None,
        "eligible": eligible,
        "exclusion_reason": reason,
        "secondary_reasons": secondary,
    }


def _decimal_equal(left, right) -> bool:
    if left is None or right is None:
        return left is None and right is None
    return abs(Decimal(str(left)) - Decimal(str(right))) <= TOLERANCE


def _normalize_timestamp(value):
    if value is None:
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(value)


def compare_sample(source: dict, database: dict) -> list[str]:
    problems = []
    for name in ("current_observation_count", "historical_sample_count_total",
                 "historical_sample_count_min", "eligible", "exclusion_reason", "secondary_reasons"):
        if source[name] != database[name]:
            problems.append(f"{name} mismatch")
    for name in ("observed_usage_kwh", "expected_usage_kwh", "component_p10_sum_kwh", "component_p90_sum_kwh"):
        if not _decimal_equal(source[name], database[name]):
            problems.append(f"{name} mismatch")
    for name in ("historical_window_start_local", "historical_window_end_exclusive_local"):
        if source[name] != database[name]:
            problems.append(f"{name} mismatch")
    source_components = source["components"]
    db_components = database["load_type_component_evidence"]
    if set(source_components) != set(db_components):
        problems.append("component load-type keys mismatch")
    for load_type, expected in source_components.items():
        actual = db_components.get(load_type)
        if actual is None:
            continue
        for name in ("current_interval_count", "historical_sample_count", "supported"):
            if expected[name] != actual[name]:
                problems.append(f"{load_type}: {name} mismatch")
        for name in ("historical_first_timestamp_local", "historical_last_timestamp_local"):
            if _normalize_timestamp(expected[name]) != _normalize_timestamp(actual[name]):
                problems.append(f"{load_type}: {name} mismatch")
        for name in ("median_15min_usage_kwh", "p10_15min_usage_kwh", "p90_15min_usage_kwh"):
            if not _decimal_equal(expected[name], actual[name]):
                problems.append(f"{load_type}: {name} mismatch")
        if not expected["every_historical_timestamp_before_hour"] or not expected["every_historical_timestamp_in_window"]:
            problems.append(f"{load_type}: historical leakage or window error")
    return problems


def _plan(conn, query: str) -> dict:
    result = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query).fetchone()[0][0]
    nodes = []

    def visit(node):
        nodes.append({"node_type": node["Node Type"], "relation": node.get("Relation Name"),
                      "index": node.get("Index Name"), "loops": node.get("Actual Loops")})
        for child in node.get("Plans", []):
            visit(child)

    visit(result["Plan"])
    return {"execution_ms": result["Execution Time"],
            "shared_hit_blocks": result["Plan"].get("Shared Hit Blocks", 0), "nodes": nodes}


def _snapshot(conn) -> dict:
    status = conn.execute("""SELECT status, hour_count FROM analytics.energy_hourly_eligibility_status
                            ORDER BY status""").fetchall()
    raw = conn.execute("""SELECT count(*), coalesce(sum(usage_kwh),0)
                          FROM raw.steel_energy_readings""").fetchone()
    runs = conn.execute("SELECT count(*) FROM monitoring.ingestion_runs").fetchone()[0]
    return {"status": status, "raw_rows": raw[0], "raw_usage_kwh": str(raw[1]), "ingestion_runs": runs}


def audit_phase4(conn, path: str | Path, source_profile: dict) -> dict:
    readings = read_source(path)
    checksum = sha256_file(path)
    problems = []
    if checksum != source_profile["source"]["sha256"] or len(readings) != source_profile["row_count"]:
        problems.append("source checksum or row count differs from Phase 1")
    before = _snapshot(conn)
    apply_baseline_models(conn)
    after_first = _snapshot(conn)
    apply_baseline_models(conn)
    after_second = _snapshot(conn)
    if before != after_first or after_first != after_second:
        problems.append("rerun changed status metrics or ingestion history")
    cursor = conn.execute("""SELECT hour_start_local, current_observation_count,
        expected_observation_count, current_coverage_pct, observed_usage_kwh,
        expected_usage_kwh, component_p10_sum_kwh, component_p90_sum_kwh,
        historical_window_start_local, historical_window_end_exclusive_local,
        historical_sample_count_total, historical_sample_count_min,
        component_count, unsupported_component_count, load_type_component_evidence,
        eligible, exclusion_reason, secondary_reasons, baseline_method_version
        FROM analytics.energy_hourly_baseline_eligibility ORDER BY hour_start_local""")
    names = [col.name for col in cursor.description]
    rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    if len(rows) != 8760 or len({row["hour_start_local"] for row in rows}) != len(rows):
        problems.append("eligibility hour count or key uniqueness")
    if sum(row["current_observation_count"] for row in rows) != len(readings):
        problems.append("current observation count reconciliation")
    for row in rows:
        if row["baseline_method_version"] != METHOD_VERSION:
            problems.append("method version mismatch")
            break
        if row["historical_window_start_local"] != row["hour_start_local"] - timedelta(days=TRAILING_DAYS) or row["historical_window_end_exclusive_local"] != row["hour_start_local"]:
            problems.append("window boundary mismatch")
            break
        if (row["eligible"] and (row["expected_usage_kwh"] is None or row["exclusion_reason"] is not None)
                or not row["eligible"] and (row["expected_usage_kwh"] is not None or row["exclusion_reason"] is None)):
            problems.append("eligibility/exclusion/expected-value inconsistency")
            break
        if row["eligible"] and (row["current_observation_count"] != 4 or row["unsupported_component_count"] != 0):
            problems.append("ineligible hour marked eligible")
            break
        if row["eligible"] and row["expected_usage_kwh"] < 0:
            problems.append("negative expectation")
            break
    statuses = conn.execute("""SELECT status, eligible, hour_count, percentage_of_observed_hours
        FROM analytics.energy_hourly_eligibility_status ORDER BY status""").fetchall()
    eligible_count = sum(1 for row in rows if row["eligible"])
    reason_counts = Counter(row["exclusion_reason"] for row in rows if not row["eligible"])
    excluded_count = sum(reason_counts.values())
    if eligible_count + excluded_count != len(rows) or sum(count for count in reason_counts.values()) != excluded_count:
        problems.append("exclusive reason count reconciliation")
    for status, eligible, count, percentage in statuses:
        expected_count = eligible_count if eligible else reason_counts.get(status, 0)
        if count != expected_count or abs(percentage - Decimal(count * 100) / len(rows)) > TOLERANCE:
            problems.append(f"status view mismatch: {status}")
    if sum(row[2] for row in statuses) != len(rows):
        problems.append("status total differs from observed hours")
    global_history_violations = conn.execute("""SELECT count(*)
        FROM analytics.energy_hourly_baseline_components
        WHERE historical_first_timestamp_local < historical_window_start_local
           OR historical_last_timestamp_local >= historical_window_end_exclusive_local""").fetchone()[0]
    if global_history_violations:
        problems.append("component history extends outside the trailing window or reaches the current hour")
    by_hour = {row["hour_start_local"]: row for row in rows}
    source_by_hour = defaultdict(list)
    for reading in readings:
        source_by_hour[reading.timestamp.replace(minute=0, second=0, microsecond=0)].append(reading)
    first = min(source_by_hour)
    hours = [first, first + timedelta(days=2, hours=12), datetime(2018, 3, 15, 10),
             datetime(2018, 3, 17, 10), datetime(2018, 12, 31, 0), max(source_by_hour)]
    later_eligible = next((hour for hour in sorted(source_by_hour) if hour >= datetime(2018, 3, 1)
                           and by_hour[hour]["eligible"]), None)
    if later_eligible is not None:
        hours.append(later_eligible)
    eligible_weekend = next((hour for hour in sorted(source_by_hour) if hour >= datetime(2018, 3, 1)
                             and by_hour[hour]["eligible"] and source_by_hour[hour][0].week_status == "Weekend"), None)
    if eligible_weekend is not None:
        hours.append(eligible_weekend)
    mixed = next((hour for hour in sorted(source_by_hour) if hour >= datetime(2018, 3, 1)
                  and len({r.load_type for r in source_by_hour[hour]}) > 1), None)
    if mixed is not None:
        hours.append(mixed)
    sample_reports = []
    for hour in dict.fromkeys(hours):
        if hour not in by_hour:
            problems.append(f"sample hour absent: {hour.isoformat()}")
            continue
        independent = evaluate_source_hour(readings, hour)
        differences = compare_sample(independent, by_hour[hour])
        if differences:
            problems.append(f"sample {hour.isoformat()}: " + ", ".join(differences))
        sample_reports.append({
            "hour_start_local": hour.isoformat(), "eligible": independent["eligible"],
            "exclusion_reason": independent["exclusion_reason"],
            "current_observation_count": independent["current_observation_count"],
            "historical_window_start_local": independent["historical_window_start_local"].isoformat(),
            "historical_window_end_exclusive_local": independent["historical_window_end_exclusive_local"].isoformat(),
            "expected_usage_kwh": str(independent["expected_usage_kwh"]) if independent["expected_usage_kwh"] is not None else None,
            "components": {load: {k: str(v) if isinstance(v, Decimal) else v for k, v in component.items()}
                           for load, component in independent["components"].items()},
            "database_comparison_passed": not differences,
        })
    plans = {
        "eligibility_status_full": _plan(conn, "SELECT * FROM analytics.energy_hourly_eligibility_status"),
        "eligibility_week_sample": _plan(conn, "SELECT hour_start_local, eligible, expected_usage_kwh FROM analytics.energy_hourly_baseline_eligibility WHERE hour_start_local >= TIMESTAMP '2018-06-01' AND hour_start_local < TIMESTAMP '2018-06-08'"),
    }
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database_version": conn.execute("SHOW server_version").fetchone()[0],
        "csv_sha256": checksum,
        "method_version": METHOD_VERSION,
        "trailing_window_days": TRAILING_DAYS,
        "minimum_comparable_samples_per_component": MIN_COMPARABLE_SAMPLES,
        "observed_hours": len(rows), "source_readings": len(readings),
        "eligible_hours": eligible_count, "excluded_hours": excluded_count,
        "exclusive_exclusion_reason_counts": dict(reason_counts),
        "status_rows": [{"status": status, "eligible": eligible, "hour_count": count,
                         "percentage_of_observed_hours": str(percentage)}
                        for status, eligible, count, percentage in statuses],
        "sampled_hours": sample_reports,
        "all_sampled_history_strictly_before_hour": all(
            component["every_historical_timestamp_before_hour"]
            for report in sample_reports for component in report["components"].values()),
        "global_component_history_window_violations": global_history_violations,
        "reapplication_snapshots_equal": before == after_first == after_second,
        "raw_rows_after_reapplication": after_second["raw_rows"],
        "raw_usage_kwh_after_reapplication": after_second["raw_usage_kwh"],
        "ingestion_runs_after_reapplication": after_second["ingestion_runs"],
        "explain_analyze": plans,
        "decimal_tolerance": str(TOLERANCE),
        "audit_status": "passed" if not problems else "failed",
        "problems": problems,
    }
