"""Small synthetic histories for exact boundaries, leakage, support and reruns."""

import csv
import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from psycopg import sql

from energyops.analytics import apply_analytics_models
from energyops.baseline import apply_baseline_models
from energyops.baseline_audit import (Reading, _snapshot, classify_eligibility,
                                      discrete_percentile, evaluate_source_hour)
from energyops.database import DatabaseConfig, initialize_database
from energyops.ingestion import ingest_csv
from energyops.provenance import sha256_file
from energyops.source_validation import COLUMN_MAP


EVALUATED = datetime(2018, 3, 1, 10)


def make_reading(stamp, value, load="Light_Load"):
    return Reading(stamp, Decimal(str(value)) if value is not None else None, load,
                   "Weekend" if stamp.weekday() >= 5 else "Weekday")


def historical_fixture():
    dates = [datetime(2018, 2, day, 10) for day in (1, 2, 5, 6, 7, 8)]
    history = []
    for index, day in enumerate(dates):
        history.extend([make_reading(day, index * 2 + 1),
                        make_reading(day + timedelta(minutes=15), index * 2 + 2),
                        make_reading(day + timedelta(minutes=30), index * 2 + 10, "Medium_Load"),
                        make_reading(day + timedelta(minutes=45), index * 2 + 11, "Medium_Load")])
    current = [make_reading(EVALUATED, 100), make_reading(EVALUATED + timedelta(minutes=15), 100),
               make_reading(EVALUATED + timedelta(minutes=30), 100, "Medium_Load"),
               make_reading(EVALUATED + timedelta(minutes=45), 100, "Medium_Load")]
    return history + current


def test_discrete_percentile_boundary_and_no_future_leakage():
    readings = historical_fixture()
    readings += [make_reading(datetime(2018, 1, 31, 10), 9999),
                 make_reading(datetime(2018, 3, 2, 10), 9999)]
    result = evaluate_source_hour(readings, EVALUATED)
    assert result["historical_window_start_local"] == datetime(2018, 2, 1, 10)
    assert result["historical_window_end_exclusive_local"] == EVALUATED
    assert result["eligible"] is True
    assert result["components"]["Light_Load"]["historical_sample_count"] == 12
    assert result["components"]["Medium_Load"]["historical_sample_count"] == 12
    assert result["components"]["Light_Load"]["historical_first_timestamp_local"] == "2018-02-01T10:00:00"
    assert result["components"]["Light_Load"]["historical_last_timestamp_local"] == "2018-02-08T10:15:00"
    assert result["expected_usage_kwh"] == Decimal("42")
    assert all(c["every_historical_timestamp_before_hour"] and c["every_historical_timestamp_in_window"]
               for c in result["components"].values())
    assert discrete_percentile([Decimal(n) for n in range(1, 13)], Decimal("0.5")) == Decimal(6)


def test_warmup_missing_load_type_and_exclusive_reasons():
    readings = historical_fixture()
    first = evaluate_source_hour(readings, datetime(2018, 2, 1, 10))
    assert first["eligible"] is False and first["exclusion_reason"] == "insufficient_baseline_support"
    missing = evaluate_source_hour(readings + [make_reading(EVALUATED + timedelta(hours=1), 5, "Maximum_Load")],
                                   EVALUATED + timedelta(hours=1))
    assert missing["expected_usage_kwh"] is None
    assert missing["exclusion_reason"] == "insufficient_current_and_baseline"
    assert classify_eligibility(2, 4, True)[1] == "insufficient_current_coverage"
    assert classify_eligibility(4, 4, False)[1] == "insufficient_baseline_support"
    both = classify_eligibility(2, 4, False)
    assert both == (False, "insufficient_current_and_baseline",
                    ["insufficient_current_coverage", "insufficient_baseline_support"])


def test_null_required_value_has_other_data_reason():
    readings = historical_fixture()
    readings[-1] = make_reading(EVALUATED + timedelta(minutes=45), None, "Medium_Load")
    result = evaluate_source_hour(readings, EVALUATED)
    assert result["eligible"] is False
    assert result["expected_usage_kwh"] is None
    assert result["exclusion_reason"] == "other_data_problem"
    assert "other_data_problem" in result["secondary_reasons"]


def write_csv(tmp_path, readings):
    path = tmp_path / "phase4_fixture.csv"
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMN_MAP)
        writer.writeheader()
        for r in sorted(readings, key=lambda item: item.timestamp):
            stamp = r.timestamp
            writer.writerow(dict(zip(COLUMN_MAP, [stamp.strftime("%d/%m/%Y %H:%M"), str(r.usage_kwh),
                                                  "0", "0", "0", "80", "90",
                                                  str(stamp.hour * 3600 + stamp.minute * 60),
                                                  r.week_status, stamp.strftime("%A"), r.load_type])))
    return path


@pytest.fixture(scope="module")
def isolated_db():
    if os.environ.get("ENERGYOPS_RUN_DB_TESTS") != "1":
        pytest.skip("set ENERGYOPS_RUN_DB_TESTS=1 for isolated PostgreSQL tests")
    config = DatabaseConfig.from_environment()
    name = "energyops_p4_test_" + uuid.uuid4().hex[:12]
    with config.connect() as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with config.for_database(name).connect() as conn:
            initialize_database(conn)
            yield conn
    finally:
        with config.connect() as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_database_composition_exclusions_and_rerun(isolated_db, tmp_path):
    conn = isolated_db
    readings = historical_fixture()
    readings += [make_reading(EVALUATED + timedelta(hours=1), 5, "Maximum_Load"),
                 make_reading(datetime(2018, 3, 2, 10), 3)]
    path = write_csv(tmp_path, readings)
    result = ingest_csv(conn, path, sha256_file(path), len(readings))
    assert result["inserted_rows"] == len(readings)
    apply_analytics_models(conn)
    apply_baseline_models(conn)
    first = _snapshot(conn)
    apply_baseline_models(conn)
    second = _snapshot(conn)
    assert first == second
    assert second["raw_rows"] == len(readings) and second["ingestion_runs"] == 1
    eligible = conn.execute("""SELECT current_observation_count, expected_usage_kwh,
        historical_sample_count_min, eligible, exclusion_reason, load_type_component_evidence
        FROM analytics.energy_hourly_baseline_eligibility WHERE hour_start_local=%s""",
        (EVALUATED,)).fetchone()
    assert eligible[:5] == (4, Decimal("42"), 12, True, None)
    assert set(eligible[5]) == {"Light_Load", "Medium_Load"}
    partial = conn.execute("""SELECT expected_usage_kwh, exclusion_reason, secondary_reasons
        FROM analytics.energy_hourly_baseline_eligibility WHERE hour_start_local=%s""",
        (EVALUATED + timedelta(hours=1),)).fetchone()
    assert partial == (None, "insufficient_current_and_baseline",
                       ["insufficient_current_coverage", "insufficient_baseline_support"])
    assert conn.execute("SELECT sum(hour_count) FROM analytics.energy_hourly_eligibility_status").fetchone()[0] == 9
