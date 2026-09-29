"""Audit Superset assets, every chart query, filtered cases and source invariants."""

import json
import os
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from setup_superset import Api, BASE  # noqa: E402
from energyops.database import DatabaseConfig  # noqa: E402


def snapshot(conn):
    return {
        "raw_rows_and_kwh": conn.execute("SELECT count(*), sum(usage_kwh) FROM raw.steel_energy_readings").fetchone(),
        "ingestion_runs": conn.execute("SELECT count(*) FROM monitoring.ingestion_runs").fetchone()[0],
        "eligibility": conn.execute("SELECT count(*) FILTER (WHERE eligible), count(*) FILTER (WHERE NOT eligible) FROM analytics.energy_hourly_baseline_eligibility").fetchone(),
        "rule_summary": conn.execute("SELECT rule_type,condition_positive_hours,sustained_incident_count FROM analytics.energy_rule_summary ORDER BY rule_type").fetchall(),
        "candidate_hours": conn.execute("SELECT count(*) FROM analytics.energy_candidate_hours").fetchone()[0],
        "combined_hours": conn.execute("SELECT count(*) FROM analytics.energy_rule_evaluation WHERE combined_priority").fetchone()[0],
    }


def check_read_only(config):
    with psycopg.connect(host=config.host, port=config.port, dbname=config.dbname,
                         user=os.environ.get("ENERGYOPS_ANALYTICS_USER", "energyops_analytics_ro"),
                         password=os.environ["ENERGYOPS_ANALYTICS_PASSWORD"], autocommit=True) as conn:
        observed = conn.execute("SELECT count(*) FROM analytics.energy_hourly").fetchone()[0]
        denied = {}
        for label, statement in (
            ("raw_select", "SELECT count(*) FROM raw.steel_energy_readings"),
            ("raw_insert", "INSERT INTO raw.steel_energy_readings DEFAULT VALUES"),
            ("analytics_write", "CREATE TABLE analytics.forbidden_phase6_test(x integer)"),
        ):
            try:
                conn.execute(statement)
                denied[label] = False
            except (psycopg.errors.InsufficientPrivilege, psycopg.errors.ReadOnlySqlTransaction):
                denied[label] = True
        if observed != 8760 or not all(denied.values()):
            raise AssertionError("analytics role access test failed")
        return {"analytics_hourly_rows_read": observed, "denied_operations": denied}


def main():
    api = Api()
    manifest = json.loads((ROOT / "superset" / "exported_assets" / "asset_manifest.json").read_text(encoding="utf-8"))
    datasets = api.get("dataset/?q=(page_size:100)")["result"]
    charts = api.get("chart/?q=(page_size:100)")["result"]
    dashboards = api.get("dashboard/?q=(page_size:100)")["result"]
    expected_chart_names = {c["title"] for c in manifest["charts"]}
    matching_charts = [c for c in charts if c["slice_name"] in expected_chart_names]
    if len(datasets) != 11 or len(matching_charts) != 28 or len(dashboards) != 3:
        raise AssertionError("Superset asset count or name uniqueness failed")
    if len({c["slice_name"] for c in matching_charts}) != 28:
        raise AssertionError("duplicate EnergyOps chart names")
    chart_results = []
    values = {}
    for chart in matching_charts:
        result = api.get(f"chart/{chart['id']}/data/")["result"][0]
        if result["status"] != "success" or result["rowcount"] == 0 or result.get("error"):
            raise AssertionError(f"chart query failed: {chart['slice_name']}")
        chart_results.append({"title": chart["slice_name"], "row_count": result["rowcount"],
                              "status": result["status"]})
        if result["rowcount"] == 1 and len(result["data"][0]) == 1:
            values[chart["slice_name"]] = next(iter(result["data"][0].values()))
    expected_values = {
        "Total historical energy · kWh": Decimal("959636.71"),
        "Observed 15-minute intervals": Decimal("35040"),
        "Observed facility-local hours": Decimal("8760"),
        "Observed interval coverage · %": Decimal("100"),
        "Rule eligibility · %": Decimal("88.60730593607306"),
        "Eligible hours": Decimal("7762"), "Excluded hours": Decimal("998"),
        "Consumption-positive hours": Decimal("1263"),
        "Distinct candidate hours": Decimal("1343"),
        "Sustained consumption incidents": Decimal("238"),
        "Power-factor-positive hours": Decimal("105"),
        "Sustained power-factor incidents": Decimal("5"),
        "Combined-priority hours": Decimal("25"),
    }
    for name, expected in expected_values.items():
        if name not in values or abs(Decimal(str(values[name])) - expected) > Decimal("0.000001"):
            raise AssertionError(f"KPI mismatch: {name}")
    dashboard_details = []
    chart_names_by_id = {c["id"]: c["slice_name"] for c in matching_charts}
    expected_select_scopes = {
        "Energy Operations Overview": {"Energy by source load type · kWh"},
        "Deviation & Incident Investigation": {"Sustained incident timeline", "Sustained investigation register"},
        "Power-Factor Review": {"Descriptive PF by source load type · %"},
    }
    for dashboard in dashboards:
        detail = api.get(f"dashboard/{dashboard['id']}")["result"]
        associated = api.get(f"dashboard/{dashboard['id']}/charts")["result"]
        metadata = json.loads(detail["json_metadata"])
        filters = metadata["native_filter_configuration"]
        date_filter = next(f for f in filters if f["filterType"] == "filter_time")
        if date_filter["defaultDataMask"]["filterState"]["value"] != "2018-01-01 : 2019-01-01":
            raise AssertionError("dashboard default time range")
        if not associated:
            raise AssertionError("dashboard has no associated charts")
        select_filter = next(f for f in filters if f["filterType"] == "filter_select")
        included = {chart_names_by_id[c["id"]] for c in associated
                    if c["id"] not in select_filter["scope"]["excluded"]}
        if included != expected_select_scopes[dashboard["dashboard_title"]]:
            raise AssertionError("load/rule filter scope mismatch")
        dashboard_details.append({"title": dashboard["dashboard_title"], "id": dashboard["id"],
                                  "associated_charts": len(associated),
                                  "filters": [f["name"] for f in filters]})
    # Query a real month using saved chart contexts, independent of the 2018 default.
    month_results = []
    for title in ("Daily energy trend · kWh", "Observed and expected · eligible kWh",
                  "Hourly lagging power-factor trend · %"):
        chart = next(c for c in matching_charts if c["slice_name"] == title)
        detail = api.get(f"chart/{chart['id']}")["result"]
        context = json.loads(detail["query_context"])
        context["queries"][0]["time_range"] = "2018-06-01 : 2018-07-01"
        result = api.post("chart/data", context)["result"][0]
        if result["status"] != "success" or not result["rowcount"]:
            raise AssertionError(f"June filter query empty: {title}")
        month_results.append({"title": title, "month": "2018-06", "row_count": result["rowcount"]})
    month_kpis = {}
    for title, expected in (("Total historical energy · kWh", Decimal("65404.64")),
                            ("Observed 15-minute intervals", Decimal("2880"))):
        chart = next(c for c in matching_charts if c["slice_name"] == title)
        context = json.loads(api.get(f"chart/{chart['id']}")["result"]["query_context"])
        context["queries"][0]["time_range"] = "2018-06-01 : 2018-07-01"
        data = api.post("chart/data", context)["result"][0]["data"]
        value = Decimal(str(next(iter(data[0].values()))))
        if abs(value - expected) > Decimal("0.000001"):
            raise AssertionError(f"June KPI mismatch: {title}")
        month_kpis[title] = str(value)
    config = DatabaseConfig.from_environment()
    with config.connect() as conn:
        before = snapshot(conn)
        access = check_read_only(config)
        after = snapshot(conn)
    if before != after or before["raw_rows_and_kwh"] != (35040, Decimal("959636.71")):
        raise AssertionError("source metrics changed during Superset verification")
    if before["eligibility"] != (7762, 998) or before["candidate_hours"] != 1343 or before["combined_hours"] != 25:
        raise AssertionError("Phase 4–5 metrics changed")
    if before["rule_summary"] != [("consumption_deviation", 1263, 238),
                                  ("lagging_power_factor_review", 105, 5)]:
        raise AssertionError("Phase 5 rule summary changed")
    evidence = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "status": "passed", "local_url": BASE, "superset_version": "3.0.0",
                "dataset_count": len(datasets), "chart_count": len(matching_charts),
                "dashboard_count": len(dashboards), "dashboards": dashboard_details,
                "chart_queries": sorted(chart_results, key=lambda item: item["title"]),
                "kpi_values": {k: str(v) for k, v in values.items() if k in expected_values},
                "june_filter_queries": month_results, "june_kpis": month_kpis,
                "select_filter_scopes": {k: sorted(v) for k, v in expected_select_scopes.items()},
                "read_only_role": access,
                "raw_rows": before["raw_rows_and_kwh"][0],
                "raw_usage_kwh": str(before["raw_rows_and_kwh"][1]),
                "ingestion_runs": before["ingestion_runs"],
                "eligibility": list(before["eligibility"]),
                "rule_summary": before["rule_summary"],
                "candidate_hours": before["candidate_hours"],
                "combined_priority_hours": before["combined_hours"]}
    out = ROOT / "evidence" / "phase6_superset_audit.json"
    out.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(f"Superset audit passed: {len(datasets)} datasets, {len(matching_charts)} charts, "
          f"{len(dashboards)} dashboards; evidence: {out}")


if __name__ == "__main__":
    main()
