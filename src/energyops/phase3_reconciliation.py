"""Independent CSV aggregation and PostgreSQL Phase 3 model checks."""

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from psycopg import sql

from .analytics import apply_analytics_models
from .provenance import sha256_file
from .source_validation import TIMESTAMP_FORMAT, validate_columns

TOLERANCE = Decimal("0.000001")
MODEL_KEYS = {
    "energy_hourly": ("hour_start_local",),
    "energy_daily": ("reading_date",),
    "energy_hourly_by_load_type": ("hour_start_local", "load_type"),
    "energy_daily_by_load_type": ("reading_date", "load_type"),
}


@dataclass
class Group:
    intervals: int = 0
    usage: Decimal = Decimal(0)
    lagging: Decimal = Decimal(0)
    leading: Decimal = Decimal(0)
    maximum: Decimal = Decimal(0)

    def add(self, usage: Decimal, lagging: Decimal, leading: Decimal) -> None:
        self.intervals += 1
        self.usage += usage
        self.lagging += lagging
        self.leading += leading
        self.maximum = max(self.maximum, usage)


def source_groups(path: str | Path) -> dict:
    groups = {name: defaultdict(Group) for name in MODEL_KEYS}
    profiles = defaultdict(Group)
    profile_hours = defaultdict(set)
    load_summary = defaultdict(Group)
    week_counts = Counter()
    hour_types = defaultdict(Counter)
    timestamps = set()
    source_rows = 0
    min_timestamp = max_timestamp = None
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        validate_columns(reader.fieldnames)
        for row in reader:
            stamp = datetime.strptime(row["date"], TIMESTAMP_FORMAT)
            hour = stamp.replace(minute=0, second=0, microsecond=0)
            day = stamp.date()
            load = row["Load_Type"]
            status = row["WeekStatus"]
            usage = Decimal(row["Usage_kWh"])
            lagging = Decimal(row["Lagging_Current_Reactive.Power_kVarh"])
            leading = Decimal(row["Leading_Current_Reactive_Power_kVarh"])
            source_rows += 1
            timestamps.add(stamp)
            min_timestamp = stamp if min_timestamp is None else min(min_timestamp, stamp)
            max_timestamp = stamp if max_timestamp is None else max(max_timestamp, stamp)
            groups["energy_hourly"][hour].add(usage, lagging, leading)
            groups["energy_daily"][day].add(usage, lagging, leading)
            groups["energy_hourly_by_load_type"][(hour, load)].add(usage, lagging, leading)
            groups["energy_daily_by_load_type"][(day, load)].add(usage, lagging, leading)
            profiles[(stamp.hour, status)].add(usage, lagging, leading)
            profile_hours[(stamp.hour, status)].add(hour)
            load_summary[load].add(usage, lagging, leading)
            week_counts[status] += 1
            hour_types[hour][load] += 1
    return {"groups": groups, "profiles": profiles, "profile_hours": profile_hours,
            "load_summary": load_summary, "week_counts": week_counts,
            "hour_types": hour_types, "timestamps": timestamps, "source_rows": source_rows,
            "minimum": min_timestamp, "maximum": max_timestamp}


def aggregate_snapshot(conn) -> dict:
    snapshot = {}
    for name in (*MODEL_KEYS, "energy_hour_of_day_profile", "energy_load_type_summary"):
        row = conn.execute(sql.SQL("SELECT count(*), coalesce(sum(total_usage_kwh),0), "
                                   "coalesce(sum(observed_interval_count),0) FROM analytics.{}")
                           .format(sql.Identifier(name))).fetchone()
        snapshot[name] = (row[0], str(row[1]), row[2])
    snapshot["raw_rows"] = conn.execute("SELECT count(*) FROM raw.steel_energy_readings").fetchone()[0]
    snapshot["ingestion_runs"] = conn.execute("SELECT count(*) FROM monitoring.ingestion_runs").fetchone()[0]
    return snapshot


def compare_group_model(conn, name: str, keys: tuple[str, ...], expected: dict, problems: list[str]) -> dict:
    fields = [sql.Identifier(key) for key in keys]
    statement = sql.SQL("SELECT {}, observed_interval_count, total_usage_kwh, "
                        "total_lagging_reactive_power_kvarh, total_leading_reactive_power_kvarh, "
                        "mean_15min_usage_kwh, max_15min_usage_kwh, "
                        "mean_lagging_power_factor_pct, mean_leading_power_factor_pct "
                        "FROM analytics.{}").format(sql.SQL(", ").join(fields), sql.Identifier(name))
    rows = conn.execute(statement).fetchall()
    observed = {}
    for row in rows:
        key = row[0] if len(keys) == 1 else tuple(row[:len(keys)])
        if key in observed:
            problems.append(f"{name}: duplicate key")
        observed[key] = row[len(keys):]
    if set(observed) != set(expected):
        problems.append(f"{name}: model keys differ from source")
    for key, group in expected.items():
        row = observed.get(key)
        if row is None:
            continue
        count, usage, lagging, leading, mean_usage, max_usage, mean_lag, mean_lead = row
        if any(value is None for value in row):
            problems.append(f"{name}: NULL metric")
            continue
        if count != group.intervals or any(abs(actual - target) > TOLERANCE for actual, target in
                                           ((usage, group.usage), (lagging, group.lagging),
                                            (leading, group.leading),
                                            (mean_usage, group.usage / group.intervals),
                                            (max_usage, group.maximum))):
            problems.append(f"{name}: aggregate mismatch at {key}")
        if usage < 0 or not (0 <= mean_lag <= 100 and 0 <= mean_lead <= 100):
            problems.append(f"{name}: invalid measure range at {key}")
    return observed


def plan_observation(conn, query: str) -> dict:
    result = conn.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + query).fetchone()[0][0]
    nodes = []

    def visit(node):
        nodes.append({"node_type": node["Node Type"], "relation": node.get("Relation Name"),
                      "index": node.get("Index Name")})
        for child in node.get("Plans", []):
            visit(child)

    visit(result["Plan"])
    return {"execution_ms": result["Execution Time"], "planning_ms": result["Planning Time"],
            "nodes": nodes, "shared_hit_blocks": result["Plan"].get("Shared Hit Blocks", 0)}


def reconcile_phase3(conn, path: str | Path, profile: dict) -> dict:
    source = source_groups(path)
    checksum = sha256_file(path)
    problems = []
    if checksum != profile["source"]["sha256"]:
        problems.append("source checksum differs from Phase 1")
    if source["source_rows"] != profile["row_count"] or len(source["timestamps"]) != source["source_rows"]:
        problems.append("source count or timestamp uniqueness")
    before = aggregate_snapshot(conn)
    apply_analytics_models(conn)
    after_first = aggregate_snapshot(conn)
    apply_analytics_models(conn)
    after_second = aggregate_snapshot(conn)
    if before != after_first or after_first != after_second:
        problems.append("view reapplication changed metrics or raw ingestion history")
    model_rows = {}
    observed_models = {}
    for name, keys in MODEL_KEYS.items():
        observed = compare_group_model(conn, name, keys, source["groups"][name], problems)
        observed_models[name] = observed
        model_rows[name] = len(observed)
    hourly = source["groups"]["energy_hourly"]
    daily = source["groups"]["energy_daily"]
    min_hour = source["minimum"].replace(minute=0, second=0, microsecond=0)
    max_hour = source["maximum"].replace(minute=0, second=0, microsecond=0)
    expected_hours = int((max_hour - min_hour).total_seconds() // 3600) + 1
    expected_days = (source["maximum"].date() - source["minimum"].date()).days + 1
    missing_hours = expected_hours - len(hourly)
    missing_days = expected_days - len(daily)
    partial_hours = sum(group.intervals != 4 for group in hourly.values())
    partial_days = sum(group.intervals != 96 for group in daily.values())
    if missing_hours or missing_days:
        problems.append("missing observed periods inside source coverage")
    for name, expected_per_period in (("energy_hourly", 4), ("energy_daily", 96)):
        key_name = MODEL_KEYS[name][0]
        coverage_rows = conn.execute(sql.SQL("SELECT {}, coverage_pct FROM analytics.{}")
                                     .format(sql.Identifier(key_name), sql.Identifier(name))).fetchall()
        coverage_by_key = dict(coverage_rows)
        for key, row in observed_models[name].items():
            count, _, _, _, _, _, _, _ = row
            coverage = coverage_by_key.get(key)
            if coverage is None or abs(coverage - Decimal(count * 100) / expected_per_period) > TOLERANCE or not 0 <= coverage <= 100:
                problems.append(f"{name}: coverage mismatch at {key}")
                break
        invalid_descriptive = conn.execute(sql.SQL("""SELECT count(*) FROM analytics.{}
            WHERE source_file_sha256 IS DISTINCT FROM %s
               OR min_lagging_power_factor_pct NOT BETWEEN 0 AND 100
               OR max_lagging_power_factor_pct NOT BETWEEN 0 AND 100
               OR min_leading_power_factor_pct NOT BETWEEN 0 AND 100
               OR max_leading_power_factor_pct NOT BETWEEN 0 AND 100""")
            .format(sql.Identifier(name)), (checksum,)).fetchone()[0]
        if invalid_descriptive:
            problems.append(f"{name}: provenance or power-factor range")
    # Check both profile views against their own CSV-derived grains.
    profile_rows = conn.execute("""SELECT hour_of_day, week_status, observed_hour_count,
        observed_interval_count, total_usage_kwh, mean_observed_hour_usage_kwh,
        mean_15min_usage_kwh FROM analytics.energy_hour_of_day_profile""").fetchall()
    if len(profile_rows) != len(source["profiles"]):
        problems.append("hour-of-day profile row count")
    if len({(row[0], row[1]) for row in profile_rows}) != len(profile_rows):
        problems.append("hour-of-day profile duplicate key")
    for hour, status, hour_count, count, usage, mean_hour, mean_interval in profile_rows:
        if any(value is None for value in (hour, status, hour_count, count, usage, mean_hour, mean_interval)):
            problems.append("hour-of-day profile NULL required metric")
            continue
        group = source["profiles"].get((hour, status))
        if (group is None or hour_count != len(source["profile_hours"][(hour, status)])
                or count != group.intervals or abs(usage - group.usage) > TOLERANCE
                or abs(mean_hour - group.usage / hour_count) > TOLERANCE
                or abs(mean_interval - group.usage / count) > TOLERANCE):
            problems.append(f"hour-of-day profile mismatch: {hour}/{status}")
    summary_rows = conn.execute("""SELECT load_type, observed_interval_count, total_usage_kwh,
        usage_share_pct FROM analytics.energy_load_type_summary""").fetchall()
    if len(summary_rows) != len(source["load_summary"]):
        problems.append("load-type summary row count")
    if len({row[0] for row in summary_rows}) != len(summary_rows):
        problems.append("load-type summary duplicate key")
    source_total = sum((group.usage for group in hourly.values()), Decimal(0))
    for load, count, usage, share in summary_rows:
        if any(value is None for value in (load, count, usage, share)):
            problems.append("load-type summary NULL required metric")
            continue
        group = source["load_summary"].get(load)
        expected_share = group.usage * 100 / source_total if group and source_total else None
        if (group is None or count != group.intervals or abs(usage - group.usage) > TOLERANCE
                or share is None or abs(share - expected_share) > TOLERANCE or not 0 <= share <= 100):
            problems.append(f"load-type summary mismatch: {load}")
    totals = {}
    for name in MODEL_KEYS:
        rows = observed_models[name].values()
        totals[name] = {"intervals": sum(row[0] for row in rows),
                        "usage_kwh": str(sum((row[1] for row in rows), Decimal(0))),
                        "lagging_reactive_power_kvarh": str(sum((row[2] for row in rows), Decimal(0))),
                        "leading_reactive_power_kvarh": str(sum((row[3] for row in rows), Decimal(0)))}
        if totals[name]["intervals"] != source["source_rows"] or abs(Decimal(totals[name]["usage_kwh"]) - source_total) > TOLERANCE:
            problems.append(f"{name}: total reconciliation")
    source_lag = sum((g.lagging for g in hourly.values()), Decimal(0))
    source_lead = sum((g.leading for g in hourly.values()), Decimal(0))
    for name in ("energy_hourly", "energy_daily"):
        if (abs(Decimal(totals[name]["lagging_reactive_power_kvarh"]) - source_lag) > TOLERANCE
                or abs(Decimal(totals[name]["leading_reactive_power_kvarh"]) - source_lead) > TOLERANCE):
            problems.append(f"{name}: reactive energy totals")
    db_week_counts = dict(conn.execute("""SELECT week_status, count(*) FROM staging.stg_energy_readings
                                      GROUP BY week_status""").fetchall())
    if db_week_counts != dict(source["week_counts"]):
        problems.append("weekday/weekend counts")
    selected_days = [day for day in (source["minimum"].date(), source["maximum"].date(),
                                    source["minimum"].date() + timedelta(days=181)) if day in daily]
    mixed_hours = [hour for hour in sorted(source["hour_types"]) if len(source["hour_types"][hour]) > 1][:3]
    plans = {
        "hourly_date_range": plan_observation(conn, "SELECT * FROM analytics.energy_hourly WHERE hour_start_local >= TIMESTAMP '2018-06-01' AND hour_start_local < TIMESTAMP '2018-06-08'"),
        "daily_date_range": plan_observation(conn, "SELECT * FROM analytics.energy_daily WHERE reading_date >= DATE '2018-06-01' AND reading_date < DATE '2018-07-01'"),
        "daily_load_type": plan_observation(conn, "SELECT * FROM analytics.energy_daily_by_load_type WHERE reading_date >= DATE '2018-06-01' AND reading_date < DATE '2018-07-01' AND load_type = 'Light_Load'"),
    }
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database_version": conn.execute("SHOW server_version").fetchone()[0],
        "csv_sha256": checksum, "source_observations": source["source_rows"],
        "source_distinct_timestamps": len(source["timestamps"]),
        "source_totals": {"usage_kwh": str(source_total),
                          "lagging_reactive_power_kvarh": str(source_lag),
                          "leading_reactive_power_kvarh": str(source_lead)},
        "model_row_counts": model_rows | {"energy_hour_of_day_profile": len(profile_rows),
                                          "energy_load_type_summary": len(summary_rows)},
        "model_totals": totals,
        "periods": {"first_hour": min_hour.isoformat(), "last_hour": max_hour.isoformat(),
                    "first_date": source["minimum"].date().isoformat(),
                    "last_date": source["maximum"].date().isoformat(),
                    "expected_hours_in_coverage": expected_hours, "missing_hours": missing_hours,
                    "expected_days_in_coverage": expected_days, "missing_days": missing_days,
                    "partial_hours": partial_hours, "partial_days": partial_days},
        "selected_daily_source_sums_kwh": {day.isoformat(): str(daily[day].usage) for day in selected_days},
        "selected_daily_database_sums_kwh": {
            day.isoformat(): str(observed_models["energy_daily"][day][1])
            for day in selected_days if day in observed_models["energy_daily"]},
        "selected_mixed_load_hours": [{"hour_start_local": hour.isoformat(),
                                       "intervals_by_load_type": dict(source["hour_types"][hour]),
                                       "source_usage_kwh": str(hourly[hour].usage)} for hour in mixed_hours],
        "load_type_counts": {name: group.intervals for name, group in source["load_summary"].items()},
        "source_week_status_counts": dict(source["week_counts"]),
        "database_week_status_counts": db_week_counts,
        "reapply_snapshots_equal": before == after_first == after_second,
        "raw_rows_after_reapply": after_second["raw_rows"],
        "ingestion_runs_after_reapply": after_second["ingestion_runs"],
        "decimal_tolerance": str(TOLERANCE), "explain_analyze": plans,
        "reconciliation_status": "passed" if not problems else "failed",
        "problems": problems,
    }
