"""Independent small-file aggregation and isolated PostgreSQL model checks."""

import csv
import os
import uuid
from datetime import datetime
from decimal import Decimal

import pytest
from psycopg import sql

from energyops.analytics import apply_analytics_models
from energyops.database import DatabaseConfig, initialize_database
from energyops.ingestion import ingest_csv
from energyops.phase3_reconciliation import aggregate_snapshot, source_groups
from energyops.provenance import sha256_file
from energyops.source_validation import COLUMN_MAP


def write_fixture(tmp_path):
    path = tmp_path / "partial_hours.csv"
    readings = [("01/01/2018 00:15", "1.25", "Light_Load"),
                ("01/01/2018 00:30", "2.50", "Medium_Load"),
                ("01/01/2018 01:00", "3.00", "Maximum_Load")]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMN_MAP)
        writer.writeheader()
        for stamp, usage, load in readings:
            parsed = datetime.strptime(stamp, "%d/%m/%Y %H:%M")
            writer.writerow(dict(zip(COLUMN_MAP, [stamp, usage, "0.50", "0.25", "0",
                                                  "80", "90", str(parsed.hour * 3600 + parsed.minute * 60),
                                                  "Weekday", "Monday", load])))
    return path


def test_source_aggregation_grains_and_totals(tmp_path):
    source = source_groups(write_fixture(tmp_path))
    hours = source["groups"]["energy_hourly"]
    days = source["groups"]["energy_daily"]
    assert len(hours) == 2 and len(days) == 1
    assert sorted(group.intervals for group in hours.values()) == [1, 2]
    assert sum((group.usage for group in hours.values()), Decimal(0)) == Decimal("6.75")
    assert sum((group.usage for group in source["groups"]["energy_hourly_by_load_type"].values()), Decimal(0)) == Decimal("6.75")


@pytest.fixture(scope="module")
def isolated_db():
    if os.environ.get("ENERGYOPS_RUN_DB_TESTS") != "1":
        pytest.skip("set ENERGYOPS_RUN_DB_TESTS=1 for isolated PostgreSQL tests")
    config = DatabaseConfig.from_environment()
    name = "energyops_p3_test_" + uuid.uuid4().hex[:12]
    with config.connect() as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with config.for_database(name).connect() as conn:
            initialize_database(conn)
            yield conn
    finally:
        with config.connect() as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_partial_coverage_load_reconciliation_and_rerun(isolated_db, tmp_path):
    conn = isolated_db
    path = write_fixture(tmp_path)
    result = ingest_csv(conn, path, sha256_file(path), 3)
    assert result["inserted_rows"] == 3 and result["rejected_rows"] == 0
    apply_analytics_models(conn)
    first = aggregate_snapshot(conn)
    apply_analytics_models(conn)
    second = aggregate_snapshot(conn)
    assert first == second
    assert second["raw_rows"] == 3 and second["ingestion_runs"] == 1
    hourly = conn.execute("""SELECT observed_interval_count, expected_interval_count,
        coverage_pct, total_usage_kwh, max_15min_usage_kwh FROM analytics.energy_hourly
        ORDER BY hour_start_local""").fetchall()
    assert hourly == [(2, 4, Decimal("50"), Decimal("3.75"), Decimal("2.50")),
                      (1, 4, Decimal("25"), Decimal("3.00"), Decimal("3.00"))]
    daily = conn.execute("""SELECT observed_interval_count, expected_interval_count,
        coverage_pct, total_usage_kwh FROM analytics.energy_daily""").fetchone()
    assert daily == (3, 96, Decimal("3.125"), Decimal("6.75"))
    split = conn.execute("""SELECT sum(observed_interval_count), sum(total_usage_kwh)
        FROM analytics.energy_hourly_by_load_type""").fetchone()
    assert split == (3, Decimal("6.75"))
    assert conn.execute("SELECT count(*) FROM analytics.energy_daily_by_load_type").fetchone()[0] == 3
    assert conn.execute("SELECT count(*) FROM analytics.energy_hour_of_day_profile").fetchone()[0] == 2
    assert conn.execute("SELECT sum(total_usage_kwh) FROM analytics.energy_load_type_summary").fetchone()[0] == Decimal("6.75")
