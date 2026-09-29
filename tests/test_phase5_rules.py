"""Exact threshold, NULL and island fixtures for the fixed candidate rules."""

import os
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from psycopg import sql

from energyops.database import DatabaseConfig
from energyops.investigation_rules import apply_investigation_models, decide_hour


def test_exact_thresholds_and_both_rules():
    result = decide_hour(True, 4, Decimal("43.33333333333333"), Decimal("33.33333333333333"), Decimal("69.99"))
    assert result["consumption_deviation_candidate"]
    assert result["lagging_power_factor_review_candidate"]
    assert result["combined_priority"]
    assert decide_hour(True, 4, Decimal("130"), Decimal("100"), Decimal("70"))["lagging_power_factor_review_candidate"] is False
    assert decide_hour(True, 4, Decimal("20"), Decimal("10"), Decimal("69"))["lagging_power_factor_review_candidate"] is True
    assert decide_hour(True, 4, Decimal("19.99"), Decimal("10"), Decimal("69"))["lagging_power_factor_review_candidate"] is False
    assert decide_hour(True, 4, Decimal("13"), Decimal("10"), Decimal("90"))["consumption_deviation_candidate"] is False
    assert decide_hour(True, 4, Decimal("40"), Decimal("30"), Decimal("90"))["consumption_deviation_candidate"] is True
    exact_relative = decide_hour(True, 4, Decimal("130"), Decimal("100"), Decimal("90"))
    assert exact_relative["deviation_pct"] == Decimal("30")
    assert exact_relative["consumption_deviation_candidate"] is True


def test_null_zero_partial_and_ineligible_suppress_flags():
    for eligible, count, usage, expected, pf in (
        (False, 4, Decimal("200"), Decimal("100"), Decimal("1")),
        (True, 3, Decimal("200"), Decimal("100"), Decimal("1")),
        (True, 4, None, Decimal("100"), Decimal("1")),
        (True, 4, Decimal("100"), None, None),
    ):
        result = decide_hour(eligible, count, usage, expected, pf)
        assert not result["consumption_deviation_candidate"]
        assert not result["lagging_power_factor_review_candidate"]
    zero = decide_hour(True, 4, Decimal("100"), Decimal("0"), Decimal("90"))
    assert zero["deviation_pct"] is None and not zero["consumption_deviation_candidate"]
    assert decide_hour(True, 4, Decimal("100"), Decimal("50"), None)["lagging_power_factor_review_candidate"] is False


@pytest.fixture(scope="module")
def isolated_rules_db():
    if os.environ.get("ENERGYOPS_RUN_DB_TESTS") != "1":
        pytest.skip("set ENERGYOPS_RUN_DB_TESTS=1 for isolated PostgreSQL tests")
    config = DatabaseConfig.from_environment()
    name = "energyops_p5_test_" + uuid.uuid4().hex[:12]
    with config.connect() as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with config.for_database(name).connect() as conn:
            conn.execute("CREATE SCHEMA analytics")
            conn.execute("""CREATE TABLE analytics.energy_hourly_baseline_eligibility (
                hour_start_local timestamp PRIMARY KEY, eligible boolean, exclusion_reason text,
                secondary_reasons text[], current_observation_count integer,
                expected_observation_count integer, current_coverage_pct numeric,
                observed_usage_kwh numeric, expected_usage_kwh numeric, component_p90_sum_kwh numeric,
                historical_window_start_local timestamp, historical_window_end_exclusive_local timestamp,
                historical_sample_count_total integer, historical_sample_count_min integer,
                load_type_component_evidence jsonb, baseline_method_version text)
            """)
            conn.execute("""CREATE TABLE analytics.energy_hourly (
                hour_start_local timestamp PRIMARY KEY, mean_lagging_power_factor_pct numeric,
                observed_interval_count integer)
            """)
            yield conn
    finally:
        with config.connect() as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_sql_islands_missing_hours_other_rule_and_rerun(isolated_rules_db):
    conn = isolated_rules_db
    origin = datetime(2018, 6, 1, 10)
    # 10-11 consumption island; 12 excluded; 13 singleton; 14 absent;
    # 15-16 power-factor island; 17 both; 18 zero baseline suppresses consumption.
    cases = [(0, True, 4, 140, 100, 90), (1, True, 4, 140, 100, 90),
             (2, False, 4, 140, None, 60), (3, True, 4, 140, 100, 90),
             (5, True, 4, 30, 25, 60), (6, True, 4, 30, 25, 60),
             (7, True, 4, 140, 100, 60), (8, True, 4, 140, 0, 90)]
    for offset, eligible, count, observed, expected, pf in cases:
        hour = origin + timedelta(hours=offset)
        conn.execute("""INSERT INTO analytics.energy_hourly_baseline_eligibility VALUES
            (%s,%s,%s,%s,%s,4,%s,%s,%s,150,%s,%s,20,20,
             '{"Light_Load":{"current_interval_count":4}}'::jsonb,'fixture')""",
            (hour, eligible, None if eligible else "insufficient_baseline_support",
             [] if eligible else ["insufficient_baseline_support"], count, count * 25,
             observed, expected, hour - timedelta(days=28), hour))
        conn.execute("INSERT INTO analytics.energy_hourly VALUES (%s,%s,%s)", (hour, pf, count))
    apply_investigation_models(conn)
    result = conn.execute("""SELECT hour_start_local,consumption_deviation_candidate,
        lagging_power_factor_review_candidate,combined_priority FROM analytics.energy_rule_evaluation
        ORDER BY hour_start_local""").fetchall()
    assert all(isinstance(flag, bool) for row in result for flag in row[1:])
    assert result[2][1:] == (False, False, False)
    assert result[-1][1:] == (False, False, False)
    assert result[-2][1:] == (True, True, True)
    groups = conn.execute("""SELECT rule_type,start_hour_local,last_candidate_hour_local,observed_hour_count,
        incident_key FROM analytics.energy_candidate_incidents ORDER BY rule_type,start_hour_local""").fetchall()
    assert [(r[0], r[1], r[2], r[3]) for r in groups] == [
        ("consumption_deviation", origin, origin + timedelta(hours=1), 2),
        ("lagging_power_factor_review", origin + timedelta(hours=5), origin + timedelta(hours=7), 3)]
    assert conn.execute("SELECT count(*) FROM analytics.energy_candidate_hours").fetchone()[0] == 6
    summary = conn.execute("SELECT rule_type,condition_positive_hours,sustained_incident_count FROM analytics.energy_rule_summary ORDER BY rule_type").fetchall()
    assert summary == [("consumption_deviation", 4, 1), ("lagging_power_factor_review", 3, 1)]
    apply_investigation_models(conn)
    assert conn.execute("SELECT rule_type,start_hour_local,last_candidate_hour_local,observed_hour_count,incident_key FROM analytics.energy_candidate_incidents ORDER BY rule_type,start_hour_local").fetchall() == groups
    assert conn.execute("SELECT count(*) FROM analytics.energy_hourly_baseline_eligibility").fetchone()[0] == len(cases)
