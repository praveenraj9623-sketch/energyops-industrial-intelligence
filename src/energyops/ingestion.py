"""Checksum-gated, audited, streaming ingestion of historical CSV rows."""

import csv
import json
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from psycopg.types.json import Jsonb

from .provenance import file_identity
from .source_validation import ALLOWED, COLUMN_MAP, TIMESTAMP_FORMAT, validate_columns

PIPELINE_VERSION = "phase2.1"
NUMBER_FIELDS = ["Usage_kWh", "Lagging_Current_Reactive.Power_kVarh",
                 "Leading_Current_Reactive_Power_kVarh", "CO2(tCO2)",
                 "Lagging_Current_Power_Factor", "Leading_Current_Power_Factor"]
INSERT_COLUMNS = ["source_timestamp_local", "usage_kwh", "lagging_reactive_power_kvarh",
                  "leading_reactive_power_kvarh", "co2_value", "lagging_power_factor_pct",
                  "leading_power_factor_pct", "seconds_from_midnight", "week_status",
                  "day_of_week", "load_type", "source_row_number", "source_filename",
                  "source_file_sha256", "ingestion_run_id", "source_timezone_status"]
INSERT_SQL = ("INSERT INTO raw.steel_energy_readings (" + ", ".join(INSERT_COLUMNS) +
              ") VALUES (" + ", ".join(["%s"] * len(INSERT_COLUMNS)) + ")")
REJECT_SQL = """INSERT INTO raw.steel_energy_rejections
    (ingestion_run_id, source_filename, source_file_sha256, source_row_number,
     raw_payload, rejection_reasons) VALUES (%s,%s,%s,%s,%s,%s)"""


def convert_row(row: dict[str, str]) -> tuple[tuple | None, list[str]]:
    """Return canonical typed fields or explicit rejection reasons."""
    reasons = []
    stamp = None
    try:
        stamp = datetime.strptime(row["date"], TIMESTAMP_FORMAT)
        if stamp.minute % 15 or stamp.second:
            reasons.append("timestamp_off_grid")
    except (ValueError, TypeError, KeyError):
        reasons.append("invalid_timestamp")
    numbers = {}
    for name in NUMBER_FIELDS:
        try:
            value = Decimal(row[name])
            if not value.is_finite():
                raise InvalidOperation
            numbers[name] = value
            if value < 0:
                reasons.append(f"negative:{name}")
            if "Power_Factor" in name and value > 100:
                reasons.append(f"power_factor_out_of_range:{name}")
        except (InvalidOperation, TypeError, KeyError):
            reasons.append(f"invalid_numeric:{name}")
    nsm = None
    try:
        nsm = int(row["NSM"])
        if not 0 <= nsm < 86400:
            reasons.append("nsm_out_of_range")
    except (ValueError, TypeError, KeyError):
        reasons.append("invalid_nsm")
    for name, allowed in ALLOWED.items():
        if row.get(name) not in allowed:
            reasons.append(f"invalid_category:{name}")
    if stamp is not None:
        if row.get("Day_of_week") in ALLOWED["Day_of_week"] and row["Day_of_week"] != stamp.strftime("%A"):
            reasons.append("day_name_mismatch")
        status = "Weekend" if stamp.weekday() >= 5 else "Weekday"
        if row.get("WeekStatus") in ALLOWED["WeekStatus"] and row["WeekStatus"] != status:
            reasons.append("week_status_mismatch")
        if nsm is not None and nsm != stamp.hour * 3600 + stamp.minute * 60:
            reasons.append("nsm_timestamp_mismatch")
    if reasons:
        return None, reasons
    return (stamp, *(numbers[name] for name in NUMBER_FIELDS), nsm, row["WeekStatus"],
            row["Day_of_week"], row["Load_Type"]), []


def already_loaded(conn, checksum: str) -> bool:
    return conn.execute("""SELECT EXISTS (SELECT 1 FROM monitoring.ingestion_runs
                           WHERE source_file_sha256 = %s AND run_status = 'completed')""",
                        (checksum,)).fetchone()[0]


def ingest_csv(conn, path: str | Path, expected_sha256: str, expected_rows: int | None = None,
               *, batch_size: int = 1000) -> dict:
    path = Path(path)
    identity = file_identity(path)
    if identity["sha256"] != expected_sha256:
        raise ValueError("Source checksum differs from the expected profile; ingestion stopped")
    run_id = uuid.uuid4()
    if already_loaded(conn, identity["sha256"]):
        with conn.transaction():
            conn.execute("""INSERT INTO monitoring.ingestion_runs
                (ingestion_run_id, source_filename, source_file_sha256, source_file_size_bytes,
                 source_expected_rows, run_status, completed_at, pipeline_version)
                VALUES (%s,%s,%s,%s,%s,'skipped_duplicate',now(),%s)""",
                (run_id, identity["filename"], identity["sha256"], identity["size_bytes"],
                 expected_rows, PIPELINE_VERSION))
        return {"ingestion_run_id": str(run_id), "run_status": "skipped_duplicate",
                "source_read_rows": 0, "accepted_rows": 0, "rejected_rows": 0,
                "inserted_rows": 0, "duplicate_rows": 0}
    with conn.transaction():
        conn.execute("""INSERT INTO monitoring.ingestion_runs
            (ingestion_run_id, source_filename, source_file_sha256, source_file_size_bytes,
             source_expected_rows, run_status, pipeline_version)
            VALUES (%s,%s,%s,%s,%s,'running',%s)""",
            (run_id, identity["filename"], identity["sha256"], identity["size_bytes"],
             expected_rows, PIPELINE_VERSION))
    counters = {"source_read_rows": 0, "accepted_rows": 0, "rejected_rows": 0,
                "inserted_rows": 0, "duplicate_rows": 0}
    try:
        with conn.transaction():
            existing = {record[0] for record in conn.execute(
                "SELECT source_timestamp_local FROM raw.steel_energy_readings")}
            seen = set()
            batch = []
            rejected = []
            min_stamp = max_stamp = None
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                validate_columns(reader.fieldnames)
                for row_number, row in enumerate(reader, start=2):
                    counters["source_read_rows"] += 1
                    values, reasons = convert_row(row)
                    if values is not None:
                        stamp = values[0]
                        if stamp in seen or stamp in existing:
                            reasons.append("duplicate_timestamp")
                            counters["duplicate_rows"] += 1
                        else:
                            seen.add(stamp)
                    if reasons:
                        counters["rejected_rows"] += 1
                        rejected.append((run_id, identity["filename"], identity["sha256"],
                                         row_number, Jsonb(row), Jsonb(reasons)))
                    else:
                        counters["accepted_rows"] += 1
                        min_stamp = stamp if min_stamp is None else min(min_stamp, stamp)
                        max_stamp = stamp if max_stamp is None else max(max_stamp, stamp)
                        batch.append((*values, row_number, identity["filename"],
                                      identity["sha256"], run_id, "unspecified"))
                    if len(batch) >= batch_size:
                        conn.cursor().executemany(INSERT_SQL, batch)
                        counters["inserted_rows"] += len(batch)
                        batch.clear()
                    if len(rejected) >= batch_size:
                        conn.cursor().executemany(REJECT_SQL, rejected)
                        rejected.clear()
            if batch:
                conn.cursor().executemany(INSERT_SQL, batch)
                counters["inserted_rows"] += len(batch)
            if rejected:
                conn.cursor().executemany(REJECT_SQL, rejected)
            if expected_rows is not None and counters["source_read_rows"] != expected_rows:
                raise ValueError("Source row count differs from the expected profile")
            if counters["source_read_rows"] != counters["accepted_rows"] + counters["rejected_rows"]:
                raise RuntimeError("Source row counts do not reconcile")
            conn.execute("""UPDATE monitoring.ingestion_runs SET source_read_rows=%s,
                accepted_rows=%s, rejected_rows=%s, inserted_rows=%s, duplicate_rows=%s,
                source_min_timestamp=%s, source_max_timestamp=%s,
                run_status='completed', completed_at=now() WHERE ingestion_run_id=%s""",
                (counters["source_read_rows"], counters["accepted_rows"], counters["rejected_rows"],
                 counters["inserted_rows"], counters["duplicate_rows"], min_stamp, max_stamp, run_id))
    except Exception as exc:
        with conn.transaction():
            conn.execute("""UPDATE monitoring.ingestion_runs SET run_status='failed',
                completed_at=now(), error_message=%s WHERE ingestion_run_id=%s""",
                (f"{type(exc).__name__}: ingestion transaction rolled back", run_id))
        raise
    return {"ingestion_run_id": str(run_id), "run_status": "completed", **counters}
