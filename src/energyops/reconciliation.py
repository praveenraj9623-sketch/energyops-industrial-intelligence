"""Independent CSV-vs-PostgreSQL reconciliation using exact Decimal sums."""

import csv
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .ingestion import convert_row
from .provenance import sha256_file

MEASURES = ("usage_kwh", "lagging_reactive_power_kvarh", "leading_reactive_power_kvarh")
TOLERANCE = Decimal("0.000001")


def source_summary(path: str | Path) -> dict:
    counts = {"load_type": Counter(), "week_status": Counter(), "day_of_week": Counter()}
    sums = {name: Decimal(0) for name in MEASURES}
    rows = 0
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            rows += 1
            values, reasons = convert_row(row)
            if reasons:
                raise ValueError("Source contains invalid values; full-source reconciliation requires valid rows")
            for index, name in enumerate(MEASURES, start=1):
                sums[name] += values[index]
            counts["load_type"][row["Load_Type"]] += 1
            counts["week_status"][row["WeekStatus"]] += 1
            counts["day_of_week"][row["Day_of_week"]] += 1
    return {"rows": rows, "sums": sums, "categories": counts}


def compare_summaries(source: dict, database: dict) -> list[str]:
    problems = []
    if source["rows"] != database["rows"]:
        problems.append("row count")
    for name in MEASURES:
        if abs(source["sums"][name] - database["sums"][name]) > TOLERANCE:
            problems.append(f"{name} sum")
    for name in source["categories"]:
        if dict(source["categories"][name]) != dict(database["categories"][name]):
            problems.append(f"{name} counts")
    return problems


def database_summary(conn) -> dict:
    row = conn.execute("""SELECT count(*), count(DISTINCT source_timestamp_local),
            min(source_timestamp_local), max(source_timestamp_local),
            coalesce(sum(usage_kwh),0), coalesce(sum(lagging_reactive_power_kvarh),0),
            coalesce(sum(leading_reactive_power_kvarh),0)
            FROM raw.steel_energy_readings""").fetchone()
    categories = {}
    for name in ("load_type", "week_status", "day_of_week"):
        categories[name] = dict(conn.execute(
            f"SELECT {name}, count(*) FROM raw.steel_energy_readings GROUP BY {name}").fetchall())
    flags = conn.execute("""SELECT count(*),
        count(*) FILTER (WHERE NOT day_name_matches),
        count(*) FILTER (WHERE NOT week_status_matches),
        count(*) FILTER (WHERE NOT seconds_from_midnight_matches)
        FROM staging.stg_energy_readings""").fetchone()
    return {"rows": row[0], "distinct_timestamps": row[1], "minimum": row[2], "maximum": row[3],
            "sums": dict(zip(MEASURES, row[4:])), "categories": categories,
            "staging_rows": flags[0], "consistency_mismatches": {
                "day_name": flags[1], "week_status": flags[2], "seconds_from_midnight": flags[3]}}


def reconcile(conn, path: str | Path, profile: dict) -> dict:
    source = source_summary(path)
    database = database_summary(conn)
    checksum = sha256_file(path)
    runs = conn.execute("""SELECT run_status, source_read_rows, accepted_rows,
        rejected_rows, inserted_rows, duplicate_rows FROM monitoring.ingestion_runs
        WHERE source_file_sha256=%s ORDER BY started_at, created_at, ingestion_run_id""",
        (checksum,)).fetchall()
    first = next((run for run in runs if run[0] == "completed"), None)
    second = next((run for run in runs if run[0] == "skipped_duplicate"), None)
    rejection_rows = conn.execute("SELECT count(*) FROM raw.steel_energy_rejections").fetchone()[0]
    version = conn.execute("SHOW server_version").fetchone()[0]
    problems = compare_summaries(source, database)
    if checksum != profile["source"]["sha256"]:
        problems.append("CSV checksum")
    if (first is None or first[1] != source["rows"] or first[2] != source["rows"]
            or first[3] != 0 or first[4] != source["rows"]):
        problems.append("first ingestion audit")
    if source["rows"] != profile["row_count"]:
        problems.append("source row count versus Phase 1 profile")
    if second is None or second[4] != 0:
        problems.append("second ingestion idempotency")
    if database["distinct_timestamps"] != source["rows"] or database["staging_rows"] != source["rows"]:
        problems.append("timestamp/staging counts")
    if database["minimum"] is None or database["minimum"].isoformat() != profile["timestamp"]["minimum"]:
        problems.append("minimum timestamp")
    if database["maximum"] is None or database["maximum"].isoformat() != profile["timestamp"]["maximum"]:
        problems.append("maximum timestamp")
    if any(database["consistency_mismatches"].values()):
        problems.append("staging consistency")
    if rejection_rows != 0:
        problems.append("rejection rows")
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "database_version": version, "csv_sha256": checksum,
        "source_rows": source["rows"], "accepted_rows": first[2] if first else None,
        "rejected_rows": first[3] if first else None,
        "inserted_rows": first[4] if first else None,
        "rejection_table_rows": rejection_rows,
        "raw_database_rows": database["rows"],
        "distinct_timestamps": database["distinct_timestamps"],
        "duplicate_timestamp_count": database["rows"] - database["distinct_timestamps"],
        "minimum_timestamp": database["minimum"].isoformat() if database["minimum"] else None,
        "maximum_timestamp": database["maximum"].isoformat() if database["maximum"] else None,
        "source_sums": {k: str(v) for k, v in source["sums"].items()},
        "database_sums": {k: str(v) for k, v in database["sums"].items()},
        "source_category_counts": {k: dict(v) for k, v in source["categories"].items()},
        "database_category_counts": database["categories"],
        "staging_rows": database["staging_rows"],
        "timestamp_consistency_mismatch_counts": database["consistency_mismatches"],
        "second_run_result": {"status": second[0], "inserted_rows": second[4]} if second else None,
        "raw_rows_after_second_run": database["rows"] if second else None,
        "decimal_tolerance": str(TOLERANCE),
        "reconciliation_status": "passed" if not problems else "failed",
        "problems": problems,
    }
