"""Idempotently register EnergyOps 2018 datasets, charts and dashboards in Superset 3.0."""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from energyops.database import DatabaseConfig  # noqa: E402

load_dotenv(ROOT / ".env", override=False)
BASE = "http://127.0.0.1:" + os.environ.get("SUPERSET_PORT", "8090")
TIME_RANGE = "2018-01-01 : 2019-01-01"
DATABASE_NAME = "EnergyOps verified analytics"

DATASETS = {
    "energy_hourly": ("hour_start_local", "One observed facility-local hour; additive kWh and kVarh. Power factor is a descriptive mean."),
    "energy_daily": ("reading_date", "One observed facility-local day; 96 expected intervals. Additive kWh and kVarh."),
    "energy_daily_by_load_type": ("reading_date", "One observed day and source load type; load classes may coexist in a day."),
    "energy_hourly_by_load_type": ("hour_start_local", "One observed hour and source load type; descriptive mean power factor by class."),
    "energy_hour_of_day_profile": (None, "48 hour-of-day by weekday/weekend groups; historical full-year profile, not date-filterable."),
    "energy_load_type_summary": (None, "Three historical source load types; full-year summary, not date-filterable."),
    "energy_hourly_baseline_eligibility": ("hour_start_local", "One observed hour; excluded hours have NULL expected kWh."),
    "energy_rule_evaluation": ("hour_start_local", "One observed hour; eligible and excluded remain distinct. Rule flags are hourly conditions."),
    "energy_candidate_hours": ("hour_start_local", "One distinct eligible condition-positive hour, including singletons."),
    "energy_candidate_incidents": ("start_hour_local", "One sustained rule-specific island; an hour can participate in both rule streams."),
    "energy_rule_summary": (None, "Two fixed rule rows for full-year totals; not date-filterable and not an hourly grain."),
}

METRICS = {
    "energy_hourly": [("usage_kwh", "Total usage (kWh)", "SUM(total_usage_kwh)", ",.2f"),
                      ("intervals", "Observed intervals", "SUM(observed_interval_count)", ",.0f"),
                      ("hours", "Observed hours", "COUNT(*)", ",.0f"),
                      ("coverage_pct", "Interval coverage (%)", "100.0 * SUM(observed_interval_count) / NULLIF(SUM(expected_interval_count), 0)", ",.2f")],
    "energy_daily": [("usage_kwh", "Daily usage (kWh)", "SUM(total_usage_kwh)", ",.2f")],
    "energy_daily_by_load_type": [("usage_kwh", "Usage by load type (kWh)", "SUM(total_usage_kwh)", ",.2f")],
    "energy_hourly_by_load_type": [("usage_kwh", "Usage by load type (kWh)", "SUM(total_usage_kwh)", ",.2f"),
                                   ("mean_pf_pct", "Descriptive mean lagging PF (%)", "AVG(mean_lagging_power_factor_pct)", ",.2f")],
    "energy_hour_of_day_profile": [("mean_hour_kwh", "Mean observed hour (kWh)", "AVG(mean_observed_hour_usage_kwh)", ",.2f")],
    "energy_load_type_summary": [("usage_kwh", "Usage by load type (kWh)", "SUM(total_usage_kwh)", ",.2f")],
    "energy_hourly_baseline_eligibility": [("eligible_hours", "Eligible hours", "SUM(CASE WHEN eligible THEN 1 ELSE 0 END)", ",.0f"),
                                            ("eligibility_pct", "Eligibility (%)", "100.0 * SUM(CASE WHEN eligible THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)", ",.2f"),
                                            ("excluded_hours", "Excluded hours", "SUM(CASE WHEN NOT eligible THEN 1 ELSE 0 END)", ",.0f")],
    "energy_rule_evaluation": [("observed_kwh", "Observed usage (kWh)", "SUM(observed_usage_kwh)", ",.2f"),
                               ("expected_kwh", "Expected usage (kWh, eligible only)", "SUM(expected_usage_kwh)", ",.2f"),
                               ("consumption_positive", "Consumption-positive hours", "SUM(CASE WHEN consumption_deviation_candidate THEN 1 ELSE 0 END)", ",.0f"),
                               ("pf_positive", "Power-factor-positive hours", "SUM(CASE WHEN lagging_power_factor_review_candidate THEN 1 ELSE 0 END)", ",.0f"),
                               ("combined", "Combined-priority hours", "SUM(CASE WHEN combined_priority THEN 1 ELSE 0 END)", ",.0f"),
                               ("mean_pf_pct", "Descriptive mean hourly lagging PF (%)", "AVG(mean_lagging_power_factor_pct)", ",.2f")],
    "energy_candidate_hours": [("distinct_candidate_hours", "Distinct candidate hours", "COUNT(*)", ",.0f")],
    "energy_candidate_incidents": [("incidents", "Sustained candidate incidents", "COUNT(*)", ",.0f")],
}


class Api:
    def __init__(self):
        self.session = requests.Session()
        login = self.session.post(BASE + "/api/v1/security/login", json={
            "username": os.environ["SUPERSET_ADMIN_USERNAME"],
            "password": os.environ["SUPERSET_ADMIN_PASSWORD"], "provider": "db"}, timeout=20)
        self.check(login, "login")
        self.session.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        self.session.headers["X-CSRFToken"] = self.get("security/csrf_token/")["result"]

    @staticmethod
    def check(response, label):
        if not response.ok:
            # Database API errors can echo a connection URI; never print response bodies.
            raise RuntimeError(f"Superset {label} failed: HTTP {response.status_code}")
        return response.json()

    def get(self, route):
        return self.check(self.session.get(BASE + "/api/v1/" + route, timeout=90), "GET " + route)

    def post(self, route, payload):
        return self.check(self.session.post(BASE + "/api/v1/" + route, json=payload, timeout=90), "POST " + route)

    def put(self, route, payload):
        return self.check(self.session.put(BASE + "/api/v1/" + route, json=payload, timeout=90), "PUT " + route)


def compose(*args):
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True,
                   stdout=subprocess.DEVNULL)


def initialize():
    compose("exec", "-T", "superset", "superset", "db", "upgrade")
    # Query the local metadata store. A rerun keeps the existing user and password.
    result = subprocess.run(["docker", "compose", "exec", "-T", "superset", "superset", "fab", "list-users"],
                            cwd=ROOT, text=True, capture_output=True, check=True)
    if os.environ["SUPERSET_ADMIN_USERNAME"] not in result.stdout:
        compose("exec", "-T", "superset", "sh", "-c",
                'superset fab create-admin --username "$SUPERSET_ADMIN_USERNAME" '
                '--firstname EnergyOps --lastname Admin --email "$SUPERSET_ADMIN_EMAIL" '
                '--password "$SUPERSET_ADMIN_PASSWORD"')
    compose("exec", "-T", "superset", "superset", "init")


def metric(expression, label):
    return {"expressionType": "SQL", "sqlExpression": expression, "label": label}


def form_and_context(dataset_id, viz, metrics=None, columns=None, time_col=None,
                     filters=None, grain=None, raw=False, limit=1000):
    metrics = metrics or []
    columns = columns or []
    filters = filters or []
    form = {"datasource": f"{dataset_id}__table", "viz_type": viz,
            "time_range": TIME_RANGE if time_col else "No filter", "row_limit": limit,
            "show_legend": True}
    if time_col:
        form["granularity_sqla"] = time_col
    if viz == "big_number_total":
        form.update(metric=metrics[0], header_font_size=0.4, subheader_font_size=0.15,
                    y_axis_format=",.2f" if ("kWh" in metrics[0]["label"] or "%" in metrics[0]["label"]) else ",.0f")
    elif viz == "table":
        form.update(query_mode="raw" if raw else "aggregate", all_columns=columns,
                    groupby=[] if raw else columns, metrics=metrics,
                    page_length=20, include_search=True)
    else:
        form.update(metrics=metrics, groupby=columns[1:],
                    x_axis=columns[0] if columns else time_col,
                    time_grain_sqla=grain, orientation="vertical", show_value=False)
    if filters:
        form["adhoc_filters"] = [{"clause": "WHERE", "expressionType": "SIMPLE",
                                  "subject": f["col"], "operator": f["op"], "comparator": f["val"]}
                                 for f in filters]
    query = {"filters": filters, "extras": {"time_grain_sqla": grain, "having": "", "where": ""},
             "applied_time_extras": {}, "columns": columns, "metrics": metrics,
             "orderby": [], "annotation_layers": [], "row_limit": limit,
             "series_limit": 0, "order_desc": True, "url_params": {},
             "custom_params": {}, "custom_form_data": {}}
    if time_col:
        query.update(granularity=time_col, time_range=TIME_RANGE)
    if raw:
        query["is_timeseries"] = False
    context = {"datasource": {"id": dataset_id, "type": "table"}, "force": False,
               "queries": [query], "form_data": form,
               "result_format": "json", "result_type": "full"}
    return form, context


def layout(title, items):
    # Each item is a sequence of chart records, or a Markdown string.
    positions = {"DASHBOARD_VERSION_KEY": "v2",
                 "ROOT_ID": {"children": ["GRID_ID"], "id": "ROOT_ID", "type": "ROOT"},
                 "GRID_ID": {"children": [], "id": "GRID_ID", "parents": ["ROOT_ID"], "type": "GRID"},
                 "HEADER_ID": {"id": "HEADER_ID", "meta": {"text": title}, "type": "HEADER"}}
    for index, item in enumerate(items):
        row_id = f"ROW-energyops-{index}"
        positions["GRID_ID"]["children"].append(row_id)
        row = {"children": [], "id": row_id,
               "meta": {"background": "BACKGROUND_TRANSPARENT"},
               "parents": ["ROOT_ID", "GRID_ID"], "type": "ROW"}
        positions[row_id] = row
        if isinstance(item, str):
            key = f"MARKDOWN-energyops-{index}"
            row["children"].append(key)
            positions[key] = {"children": [], "id": key,
                              "meta": {"code": item, "height": 12, "width": 12},
                              "parents": ["ROOT_ID", "GRID_ID", row_id], "type": "MARKDOWN"}
        else:
            width = 12 // len(item)
            for chart in item:
                key = f"CHART-{chart['id']}"
                row["children"].append(key)
                positions[key] = {"children": [], "id": key,
                                  "meta": {"chartId": chart["id"], "height": 32 if len(item) >= 3 else 50,
                                           "sliceName": chart["slice_name"], "uuid": chart["uuid"], "width": width},
                                  "parents": ["ROOT_ID", "GRID_ID", row_id], "type": "CHART"}
    return positions


def main():
    config = DatabaseConfig.from_environment()
    password = os.environ.get("ENERGYOPS_ANALYTICS_PASSWORD", "")
    if not password or password.startswith("replace-with-"):
        raise SystemExit("Generate the ignored local analytics password first")
    # The role script is idempotent and never prints credentials.
    subprocess.run([sys.executable, str(ROOT / "scripts" / "setup_analytics_role.py")],
                   cwd=ROOT, check=True, stdout=subprocess.DEVNULL)
    initialize()
    api = Api()
    databases = api.get("database/")["result"]
    existing_db = next((d for d in databases if d["database_name"] == DATABASE_NAME), None)
    uri = ("postgresql+psycopg2://" + os.environ.get("ENERGYOPS_ANALYTICS_USER", "energyops_analytics_ro")
           + ":" + quote_plus(password) + "@energyops-db:5432/" + config.dbname)
    db_payload = {"database_name": DATABASE_NAME, "sqlalchemy_uri": uri,
                  "expose_in_sqllab": False, "allow_ctas": False, "allow_cvas": False,
                  "allow_dml": False, "allow_file_upload": False}
    if existing_db:
        db_id = existing_db["id"]
        api.put(f"database/{db_id}", db_payload)
    else:
        db_id = api.post("database/", db_payload)["id"]
    dataset_existing = {(d["schema"], d["table_name"]): d for d in api.get("dataset/?q=(page_size:100)")["result"]}
    datasets = {}
    for name, (time_col, description) in DATASETS.items():
        found = dataset_existing.get(("analytics", name))
        dataset_id = found["id"] if found else api.post("dataset/", {
            "database": db_id, "schema": "analytics", "table_name": name})["id"]
        definitions = [{"metric_name": code, "verbose_name": label, "expression": expression,
                        "description": f"{label}; {expression}", "d3format": fmt}
                       for code, label, expression, fmt in METRICS.get(name, [])]
        existing_metrics = {m["metric_name"]: m["id"] for m in
                            api.get(f"dataset/{dataset_id}")["result"]["metrics"]}
        for definition in definitions:
            if definition["metric_name"] in existing_metrics:
                definition["id"] = existing_metrics[definition["metric_name"]]
        payload = {"description": description, "metrics": definitions}
        if time_col:
            payload["main_dttm_col"] = time_col
        api.put(f"dataset/{dataset_id}", payload)
        datasets[name] = dataset_id
    chart_existing = {c["slice_name"]: c for c in api.get("chart/?q=(page_size:100)")["result"]}
    charts = {}

    def add(name, dataset, viz, expression=None, label=None, columns=None, filters=None,
            grain=None, raw=False, limit=1000, other_metrics=None):
        ds_id = datasets[dataset]
        measures = [metric(expression, label)] if expression else []
        measures.extend(metric(exp, lbl) for exp, lbl in (other_metrics or []))
        form, context = form_and_context(ds_id, viz, measures, columns, DATASETS[dataset][0],
                                         filters, grain, raw, limit)
        payload = {"slice_name": name, "datasource_id": ds_id, "datasource_type": "table",
                   "viz_type": viz, "params": json.dumps(form),
                   "query_context": json.dumps(context), "query_context_generation": True,
                   "description": f"EnergyOps 2018 verified analytics. {label or name}."}
        found = chart_existing.get(name)
        chart_id = found["id"] if found else api.post("chart/", payload)["id"]
        if found:
            api.put(f"chart/{chart_id}", payload)
        charts[name] = {"id": chart_id, "slice_name": name,
                        "dataset": dataset, "viz": viz}

    # Operations overview: all-load totals and a load-class decomposition are kept separate.
    add("Total historical energy · kWh", "energy_hourly", "big_number_total", "SUM(total_usage_kwh)", "kWh")
    add("Observed 15-minute intervals", "energy_hourly", "big_number_total", "SUM(observed_interval_count)", "intervals")
    add("Observed facility-local hours", "energy_hourly", "big_number_total", "COUNT(*)", "hours")
    add("Observed interval coverage · %", "energy_hourly", "big_number_total", "100.0 * SUM(observed_interval_count) / NULLIF(SUM(expected_interval_count),0)", "coverage %")
    add("Daily energy trend · kWh", "energy_daily", "echarts_timeseries_line", "SUM(total_usage_kwh)", "kWh", ["reading_date"], grain="P1D")
    add("Energy by source load type · kWh", "energy_daily_by_load_type", "echarts_timeseries_bar", "SUM(total_usage_kwh)", "kWh", ["load_type"])
    add("Hour-of-day · weekday and weekend", "energy_hour_of_day_profile", "echarts_timeseries_bar", "AVG(mean_observed_hour_usage_kwh)", "mean kWh per observed hour", ["hour_of_day", "week_status"])
    add("Daily interval coverage · %", "energy_daily", "echarts_timeseries_line", "100.0 * SUM(observed_interval_count) / NULLIF(SUM(expected_interval_count),0)", "coverage %", ["reading_date"], grain="P1D")

    # Investigation: all percentages use observed-hour counts, never incident rows.
    add("Rule eligibility · %", "energy_hourly_baseline_eligibility", "big_number_total", "100.0 * SUM(CASE WHEN eligible THEN 1 ELSE 0 END) / NULLIF(COUNT(*),0)", "eligible %")
    add("Eligible hours", "energy_hourly_baseline_eligibility", "big_number_total", "SUM(CASE WHEN eligible THEN 1 ELSE 0 END)", "eligible hours")
    add("Excluded hours", "energy_hourly_baseline_eligibility", "big_number_total", "SUM(CASE WHEN NOT eligible THEN 1 ELSE 0 END)", "excluded hours")
    add("Consumption-positive hours", "energy_rule_evaluation", "big_number_total", "SUM(CASE WHEN consumption_deviation_candidate THEN 1 ELSE 0 END)", "positive hours")
    add("Distinct candidate hours", "energy_candidate_hours", "big_number_total", "COUNT(*)", "distinct hours")
    add("Sustained consumption incidents", "energy_candidate_incidents", "big_number_total", "COUNT(*)", "rule-specific incidents", filters=[{"col":"rule_type","op":"==","val":"consumption_deviation"}])
    add("Exclusion reasons · observed hours", "energy_hourly_baseline_eligibility", "echarts_timeseries_bar", "COUNT(*)", "excluded hours", ["exclusion_reason"], filters=[{"col":"eligible","op":"==","val":False}])
    add("Eligibility and hourly baseline detail", "energy_hourly_baseline_eligibility", "table", columns=["hour_start_local","current_observation_count","observed_usage_kwh","expected_usage_kwh","eligible","exclusion_reason","historical_sample_count_min"], raw=True, limit=100)
    add("Observed and expected · eligible kWh", "energy_rule_evaluation", "echarts_timeseries_line", "SUM(observed_usage_kwh)", "observed kWh", ["hour_start_local"], filters=[{"col":"eligible","op":"==","val":True}], grain="P1M", other_metrics=[("SUM(expected_usage_kwh)","expected kWh")])
    add("Deviation candidate detail", "energy_candidate_hours", "table", columns=["hour_start_local","observed_usage_kwh","expected_usage_kwh","excess_kwh","deviation_pct","consumption_deviation_candidate","lagging_power_factor_review_candidate"], raw=True, limit=50)
    add("Sustained incident timeline", "energy_candidate_incidents", "echarts_timeseries_bar", "COUNT(*)", "incidents", ["start_hour_local"], grain="P1M")
    add("Sustained investigation register", "energy_candidate_incidents", "table", columns=["rule_type","start_hour_local","last_candidate_hour_local","observed_hour_count","peak_observed_usage_kwh","peak_positive_excess_kwh","peak_signed_deviation_pct","minimum_mean_lagging_power_factor_pct","status"], raw=True, limit=100)

    # Power-factor review: PF means are descriptive, reactive energy stays additive.
    add("Power-factor-positive hours", "energy_rule_evaluation", "big_number_total", "SUM(CASE WHEN lagging_power_factor_review_candidate THEN 1 ELSE 0 END)", "review hours")
    add("Sustained power-factor incidents", "energy_candidate_incidents", "big_number_total", "COUNT(*)", "rule-specific incidents", filters=[{"col":"rule_type","op":"==","val":"lagging_power_factor_review"}])
    add("Combined-priority hours", "energy_rule_evaluation", "big_number_total", "SUM(CASE WHEN combined_priority THEN 1 ELSE 0 END)", "hours with both rules")
    add("Hourly lagging power-factor trend · %", "energy_hourly", "echarts_timeseries_line", "AVG(mean_lagging_power_factor_pct)", "mean PF %", ["hour_start_local"], grain="P1D")
    add("Usage context for power-factor review · kWh", "energy_rule_evaluation", "echarts_timeseries_line", "SUM(observed_usage_kwh)", "observed kWh", ["hour_start_local"], grain="P1M")
    add("Lagging reactive energy · kVarh", "energy_hourly", "echarts_timeseries_line", "SUM(total_lagging_reactive_power_kvarh)", "lagging kVarh", ["hour_start_local"], grain="P1M")
    add("Descriptive PF by source load type · %", "energy_hourly_by_load_type", "echarts_timeseries_bar", "AVG(mean_lagging_power_factor_pct)", "mean PF %", ["load_type"])
    add("Power-factor investigation register", "energy_candidate_incidents", "table", columns=["start_hour_local","last_candidate_hour_local","observed_hour_count","peak_observed_usage_kwh","minimum_mean_lagging_power_factor_pct","status"], filters=[{"col":"rule_type","op":"==","val":"lagging_power_factor_review"}], raw=True, limit=30)

    # Superset 3.0's chart detail API omits UUID, while its dashboard layout needs it.
    uuids = subprocess.run(["docker", "compose", "exec", "-T", "superset-metadata", "sh", "-c",
                            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At -F , '
                            '-c "SELECT id, uuid FROM slices"'],
                           cwd=ROOT, text=True, capture_output=True, check=True)
    uuid_by_id = {int(line.split(",", 1)[0]): line.split(",", 1)[1]
                  for line in uuids.stdout.splitlines() if "," in line}
    for chart in charts.values():
        chart["uuid"] = uuid_by_id[chart["id"]]

    dash_definitions = [
        ("Energy Operations Overview", "energy-operations-overview", [
            "**Historical 2018 facility-local data.** Energy is kWh; coverage = observed intervals / expected intervals. Load classes are source interval labels, not whole-hour states.",
            ["Total historical energy · kWh","Observed 15-minute intervals","Observed facility-local hours","Observed interval coverage · %"],
            ["Daily energy trend · kWh","Energy by source load type · kWh"],
            ["Hour-of-day · weekday and weekend","Daily interval coverage · %"]],
         ["Total historical energy · kWh","Observed 15-minute intervals","Observed facility-local hours","Observed interval coverage · %","Daily energy trend · kWh","Energy by source load type · kWh","Daily interval coverage · %"],
         [("Load type", "filter_select", "energy_daily_by_load_type", "load_type", ["Energy by source load type · kWh"])]),
        ("Deviation & Incident Investigation", "deviation-incident-investigation", [
            "**Candidate review heuristic:** consumption is at least **10 kWh AND 30% above expected**. Sustained means at least **two consecutive qualifying hours for the same rule**. Excluded hours are not healthy evaluations. Historical 2018 data, not a live feed.",
            ["Rule eligibility · %","Eligible hours","Excluded hours","Consumption-positive hours"],
            ["Distinct candidate hours","Sustained consumption incidents"],
            ["Exclusion reasons · observed hours","Observed and expected · eligible kWh"],
            ["Eligibility and hourly baseline detail"],
            ["Sustained incident timeline","Deviation candidate detail"],
            ["Sustained investigation register"]],
         ["Rule eligibility · %","Eligible hours","Excluded hours","Consumption-positive hours","Distinct candidate hours","Sustained consumption incidents","Exclusion reasons · observed hours","Observed and expected · eligible kWh","Eligibility and hourly baseline detail","Sustained incident timeline","Deviation candidate detail","Sustained investigation register"],
         [("Rule type", "filter_select", "energy_candidate_incidents", "rule_type", ["Sustained incident timeline","Sustained investigation register"])]),
        ("Power-Factor Review", "power-factor-review", [
            "**Candidate review heuristic:** mean of four 15-minute lagging power-factor percentages **below 70%**, with at least **20 kWh observed**. Sustained means **two consecutive qualifying hours for the same rule**. Mean PF is descriptive, not a billing aggregate or plant operating limit.",
            ["Power-factor-positive hours","Sustained power-factor incidents","Combined-priority hours"],
            ["Hourly lagging power-factor trend · %","Usage context for power-factor review · kWh"],
            ["Lagging reactive energy · kVarh","Descriptive PF by source load type · %"],
            ["Power-factor investigation register"]],
         ["Power-factor-positive hours","Sustained power-factor incidents","Combined-priority hours","Hourly lagging power-factor trend · %","Usage context for power-factor review · kWh","Lagging reactive energy · kVarh","Descriptive PF by source load type · %","Power-factor investigation register"],
         [("Load type", "filter_select", "energy_hourly_by_load_type", "load_type", ["Descriptive PF by source load type · %"])]),
    ]
    dashboard_existing = {d["dashboard_title"]: d for d in api.get("dashboard/?q=(page_size:100)")["result"]}
    dashboards = {}
    for title, slug, rows, date_scope, extra_filters in dash_definitions:
        used = [charts[name] for item in rows if not isinstance(item, str) for name in item]
        positions = layout(title, [item if isinstance(item, str) else [charts[name] for name in item] for item in rows])
        filters = [{"id": "NATIVE_FILTER-energyops-date", "name": "2018 date range", "filterType": "filter_time",
                    "targets": [{}], "defaultDataMask": {"extraFormData": {"time_range": TIME_RANGE},
                                                       "filterState": {"value": TIME_RANGE}},
                    "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"],
                                                        "excluded": [c["id"] for c in used if c["slice_name"] not in date_scope]},
                    "type": "NATIVE_FILTER"}]
        for label, filter_type, dataset, column, applies_to in extra_filters:
            filters.append({"id": "NATIVE_FILTER-energyops-" + column.replace("_", "-"),
                            "name": label, "filterType": filter_type,
                            "targets": [{"datasetId": datasets[dataset], "column": {"name": column}}],
                            "controlValues": {"multiSelect": True, "searchAllOptions": False,
                                              "inverseSelection": False, "enableEmptyFilter": False},
                            "cascadeParentIds": [], "scope": {"rootPath": ["ROOT_ID"],
                                                                  "excluded": [c["id"] for c in used if c["slice_name"] not in applies_to]},
                            "type": "NATIVE_FILTER"})
        metadata = {"native_filter_configuration": filters, "refresh_frequency": 0,
                    "default_filters": "{}", "color_scheme": "supersetColors"}
        payload = {"dashboard_title": title, "slug": slug, "published": True,
                   "position_json": json.dumps(positions), "json_metadata": json.dumps(metadata)}
        found = dashboard_existing.get(title)
        dashboard_id = found["id"] if found else api.post("dashboard/", payload)["id"]
        if found:
            api.put(f"dashboard/{dashboard_id}", payload)
        api.put(f"dashboard/{dashboard_id}", {"position_json": json.dumps(positions),
                                               "json_metadata": json.dumps(metadata)})
        for chart in used:
            api.put(f"chart/{chart['id']}", {"dashboards": [dashboard_id]})
        dashboards[title] = {"id": dashboard_id, "url": BASE + "/superset/dashboard/" + str(dashboard_id) + "/",
                             "charts": len(used), "filters": [f["name"] for f in filters]}
    export = {"source": "EnergyOps verified analytics views", "superset_version": "3.0.0",
              "database_name": DATABASE_NAME,
              "datasets": [{"schema": "analytics", "view": name, "time_column": item[0],
                            "description": item[1], "metrics": METRICS.get(name, [])}
                           for name, item in DATASETS.items()],
              "charts": [{"title": name, "dataset": item["dataset"], "viz_type": item["viz"]}
                         for name, item in charts.items()],
              "dashboards": dashboards, "default_time_range": TIME_RANGE}
    output = ROOT / "superset" / "exported_assets" / "asset_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(export, indent=2) + "\n", encoding="utf-8")
    print(f"Superset assets: {len(datasets)} datasets, {len(charts)} charts, {len(dashboards)} dashboards.")
    for title, details in dashboards.items():
        print(f"{title}: {details['url']}")


if __name__ == "__main__":
    main()
