"""Public export integrity and grain-sensitive filter checks."""

from datetime import date
from pathlib import Path

import pytest

from energyops.public_snapshot import (
    load_snapshot, period_metrics, select_dates, weighted_pf_by_load,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def snapshot():
    return load_snapshot(ROOT / "data" / "export")


def test_full_year_reconciles_without_database(snapshot):
    manifest, tables = snapshot
    values = period_metrics(tables["hourly"], tables["eligibility"],
                            tables["candidate_hours"], tables["incidents"])
    assert values == {
        "usage_kwh": pytest.approx(959636.71), "intervals": 35040,
        "observed_hours": 8760, "eligible_hours": 7762, "excluded_hours": 998,
        "candidate_hours": 1343, "consumption_positive_hours": 1263,
        "pf_positive_hours": 105, "combined_priority_hours": 25,
        "consumption_incidents": 238, "pf_incidents": 5,
    }
    assert manifest["source_readings"] == 35040
    assert tables["eligibility"].loc[~tables["eligibility"]["eligible"],
                                      "expected_usage_kwh"].isna().all()


def test_month_filter_and_load_grains(snapshot):
    _, tables = snapshot
    june = date(2018, 6, 1), date(2018, 6, 30)
    hourly = select_dates(tables["hourly"], "hour_start_local", *june)
    daily = select_dates(tables["daily"], "reading_date", *june)
    load = select_dates(tables["daily_by_load_type"], "reading_date", *june)
    assert len(hourly) == 720
    assert int(hourly["observed_interval_count"].sum()) == 2880
    assert round(hourly["total_usage_kwh"].sum(), 2) == 65404.64
    assert round(load["total_usage_kwh"].sum(), 2) == round(daily["total_usage_kwh"].sum(), 2)
    light = load[load["load_type"] == "Light_Load"]
    assert light["total_usage_kwh"].sum() < hourly["total_usage_kwh"].sum()
    assert not weighted_pf_by_load(light).empty


def test_incident_and_candidate_grains(snapshot):
    _, tables = snapshot
    candidate = tables["candidate_hours"]
    incident = tables["incidents"]
    assert candidate["hour_start_local"].is_unique
    assert incident["incident_key"].is_unique
    assert incident.groupby("rule_type").size().to_dict() == {
        "consumption_deviation": 238, "lagging_power_factor_review": 5}
    assert candidate["combined_priority"].sum() == 25
