"""Public, snapshot-only EnergyOps presentation. No runtime database or network access."""

from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from energyops.public_snapshot import (  # noqa: E402
    load_snapshot, period_metrics, select_dates, weighted_pf_by_load,
)

st.set_page_config(page_title="EnergyOps | Industrial Energy Intelligence",
                   page_icon="⚡", layout="wide")
st.markdown("""
<style>
  .stApp {background:#f5f8fb; color:#152536}
  .block-container {padding-top:1.6rem; max-width:1450px}
  h1,h2,h3 {color:#12304a; letter-spacing:-.025em}
  [data-testid="stMetric"] {background:white; border:1px solid #dce7ed;
    border-radius:12px; padding:15px 18px; box-shadow:0 3px 14px rgba(18,48,74,.04)}
  [data-testid="stMetricLabel"] {color:#526679}
  [data-testid="stMetricValue"] {color:#12304a !important; font-size:1.5rem !important}
  [data-testid="stMetricLabel"] p {font-size:.86rem !important; white-space:normal !important}
  .hero {background:linear-gradient(120deg,#10324a,#146577); border-radius:16px;
    color:white; padding:27px 31px; margin-bottom:18px}
  .hero h1 {color:white; font-size:2.25rem; margin:0 0 8px 0}
  .hero p {margin:0; color:#d8edf1; font-size:1rem}
  .source-band {background:#e7f2f4; border-left:5px solid #0a91a1;
    border-radius:8px; padding:14px 17px; margin:12px 0 22px 0}
  .fine {color:#526679; font-size:.9rem}
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def data():
    return load_snapshot(ROOT / "data" / "export")


try:
    manifest, tables = data()
except (OSError, ValueError) as exc:
    st.error(f"Committed public snapshot could not be verified: {exc}")
    st.stop()

st.markdown("""<div class="hero"><h1>EnergyOps · Industrial Energy Intelligence</h1>
<p>Historical 2018 energy observations · review candidates · source-backed public presentation</p></div>""",
            unsafe_allow_html=True)
st.markdown("""<div class="source-band"><strong>Apache Superset 3.0 is the primary local SQL dashboard layer.</strong>
This Streamlit app is the public presentation layer, served entirely from a verified, committed snapshot.
Explore the actual Superset dashboard captures in the <strong>Superset dashboards</strong> tab.</div>""",
            unsafe_allow_html=True)

first_date = tables["daily"]["reading_date"].min().date()
last_date = tables["daily"]["reading_date"].max().date()
st.sidebar.header("Explore 2018")
chosen = st.sidebar.date_input("Facility-local date range (inclusive)",
                               value=(first_date, last_date), min_value=first_date,
                               max_value=last_date)
if not isinstance(chosen, tuple) or len(chosen) != 2:
    st.sidebar.info("Choose both range endpoints to update the charts.")
    start_date, end_date = first_date, last_date
else:
    start_date, end_date = chosen
load_classes = sorted(tables["daily_by_load_type"]["load_type"].unique())
selected_load = st.sidebar.multiselect("Load classes in load-specific charts",
                                        load_classes, default=load_classes)
incident_rule = st.sidebar.selectbox("Incident register rule", [
    "All rules", "Consumption deviation", "Lagging power factor review"])
st.sidebar.caption("Load class and rule selectors apply only to charts at those grains. "
                   "All-hour KPIs retain their full population.")

hourly = select_dates(tables["hourly"], "hour_start_local", start_date, end_date)
daily = select_dates(tables["daily"], "reading_date", start_date, end_date)
daily_load = select_dates(tables["daily_by_load_type"], "reading_date", start_date, end_date)
eligibility = select_dates(tables["eligibility"], "hour_start_local", start_date, end_date)
candidate = select_dates(tables["candidate_hours"], "hour_start_local", start_date, end_date)
# An incident belongs to the period containing its first qualifying hour.
incidents = select_dates(tables["incidents"], "start_hour_local", start_date, end_date)
metrics = period_metrics(hourly, eligibility, candidate, incidents)
load_view = daily_load[daily_load["load_type"].isin(selected_load)].copy()
rule_codes = {"Consumption deviation": "consumption_deviation",
              "Lagging power factor review": "lagging_power_factor_review"}
incident_view = incidents if incident_rule == "All rules" else incidents[
    incidents["rule_type"] == rule_codes[incident_rule]].copy()
period_label = f"{start_date:%d %b %Y}–{end_date:%d %b %Y}"
all_year = start_date == first_date and end_date == last_date


def chart(fig, *, height=350):
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=28, b=8),
                      paper_bgcolor="white", plot_bgcolor="white",
                      font=dict(color="#294052"), legend_title_text="")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e8eef2", zeroline=False)
    st.plotly_chart(fig, width="stretch")


def download(label, frame, filename):
    st.download_button(label, frame.to_csv(index=False).encode("utf-8"),
                       file_name=filename, mime="text/csv")


tabs = st.tabs(["Executive overview", "Energy trends", "Deviation investigation",
                "Power-factor review", "Superset dashboards", "Data definitions"])

with tabs[0]:
    st.subheader("Verified full-year 2018 benchmark")
    st.caption("These ten values are fixed source reconciliations and do not change with the sidebar filters.")
    full = manifest["totals"]
    rows = [
        [("Energy · kWh", f"{float(full['usage_kwh']):,.2f}"),
         ("Observed intervals", f"{int(full['observed_intervals']):,}"),
         ("Observed hours", f"{int(full['observed_hours']):,}"),
         ("Eligible hours", f"{int(full['eligible_hours']):,}")],
        [("Excluded hours", f"{int(full['excluded_hours']):,}"),
         ("Distinct candidate hours", f"{int(full['distinct_candidate_hours']):,}"),
         ("Sustained consumption incidents", f"{int(full['consumption_incidents']):,}"),
         ("PF-positive hours", f"{int(full['pf_positive_hours']):,}")],
        [("Sustained PF incidents", f"{int(full['pf_incidents']):,}"),
         ("Combined-priority hours", f"{int(full['combined_priority_hours']):,}")],
    ]
    for row in rows:
        for column, (label, value) in zip(st.columns(len(row)), row):
            column.metric(label, value)
    st.divider()
    st.subheader(f"Selected period · {period_label}")
    for column, (label, value) in zip(st.columns(4), [
        ("Energy · kWh", f"{metrics['usage_kwh']:,.2f}"),
        ("Observed intervals", f"{metrics['intervals']:,}"),
        ("Eligible / observed hours", f"{metrics['eligible_hours']:,} / {metrics['observed_hours']:,}"),
        ("Distinct candidate hours", f"{metrics['candidate_hours']:,}"),
    ]):
        column.metric(label, value)
    left, right = st.columns([2, 1])
    with left:
        st.markdown("#### Daily energy")
        fig = px.area(daily, x="reading_date", y="total_usage_kwh",
                      labels={"reading_date": "Facility-local date", "total_usage_kwh": "kWh"},
                      color_discrete_sequence=["#167f92"])
        chart(fig)
    with right:
        st.markdown("#### Eligibility")
        status = pd.DataFrame({"Status": ["Eligible", "Excluded"],
                               "Observed hours": [metrics["eligible_hours"], metrics["excluded_hours"]]})
        fig = px.pie(status, names="Status", values="Observed hours", hole=.62,
                     color="Status", color_discrete_map={"Eligible": "#0f8795", "Excluded": "#e2a849"})
        chart(fig)
    st.info("Historical 2018 data. Candidate rules identify hours for engineering review; "
            "they do not confirm waste, faults, or savings.")

with tabs[1]:
    st.subheader(f"Energy trends · {period_label}")
    st.caption("All-hour totals and source load classes are shown separately because multiple classes can occur in one hour.")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Daily consumption · kWh")
        chart(px.line(daily, x="reading_date", y="total_usage_kwh", markers=False,
                      labels={"reading_date": "Date", "total_usage_kwh": "kWh"},
                      color_discrete_sequence=["#147d91"]))
    with right:
        st.markdown("#### Daily load-class composition · kWh")
        if load_view.empty:
            st.info("Select a load class to show this chart.")
        else:
            chart(px.area(load_view, x="reading_date", y="total_usage_kwh", color="load_type",
                          labels={"reading_date": "Date", "total_usage_kwh": "kWh"},
                          color_discrete_sequence=["#0f718c", "#4caba9", "#e6ac54"]))
    left, right = st.columns(2)
    with left:
        st.markdown("#### Mean observed hour by clock hour")
        profile = hourly.assign(clock_hour=hourly["hour_start_local"].dt.hour,
                                day_kind=hourly["hour_start_local"].dt.dayofweek.map(
                                    lambda day: "Weekend" if day >= 5 else "Weekday"))
        profile = profile.groupby(["clock_hour", "day_kind"], as_index=False)[
            "total_usage_kwh"].mean()
        chart(px.line(profile, x="clock_hour", y="total_usage_kwh", color="day_kind",
                      labels={"clock_hour": "Facility-local hour", "total_usage_kwh": "Mean kWh per observed hour"},
                      color_discrete_map={"Weekday": "#147d91", "Weekend": "#e4a24f"}))
    with right:
        st.markdown("#### Observed interval coverage")
        coverage = 100 * metrics["intervals"] / max(1, int(hourly["expected_interval_count"].sum()))
        st.metric("Selected-period coverage", f"{coverage:.2f}%")
        by_load = load_view.groupby("load_type", as_index=False)["total_usage_kwh"].sum()
        if not by_load.empty:
            chart(px.bar(by_load, x="load_type", y="total_usage_kwh",
                         labels={"load_type": "Source load class", "total_usage_kwh": "kWh"},
                         color="load_type", color_discrete_sequence=["#0f718c", "#4caba9", "#e6ac54"]),
                  height=270)
    download("Download selected daily energy CSV", daily, "energyops_daily_selected.csv")

with tabs[2]:
    st.subheader(f"Deviation investigation · {period_label}")
    st.caption("Consumption candidate: at least 10 kWh AND 30% above its supported historical expectation. "
               "Sustained: at least two consecutive qualifying hours for the same rule.")
    for column, (label, value) in zip(st.columns(4), [
        ("Eligible hours", metrics["eligible_hours"]),
        ("Excluded hours", metrics["excluded_hours"]),
        ("Consumption-positive hours", metrics["consumption_positive_hours"]),
        ("Sustained consumption incidents", metrics["consumption_incidents"]),
    ]):
        column.metric(label, f"{value:,}")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Observed versus expected · eligible hours")
        supported = eligibility[eligibility["eligible"]].copy()
        if supported.empty:
            st.info("No supported baseline in this selected period.")
        else:
            monthly = supported.assign(month=supported["hour_start_local"].dt.to_period("M").dt.to_timestamp())
            monthly = monthly.groupby("month", as_index=False)[["observed_usage_kwh", "expected_usage_kwh"]].sum()
            long = monthly.melt(id_vars="month", var_name="Series", value_name="kWh")
            long["Series"] = long["Series"].map({"observed_usage_kwh": "Observed", "expected_usage_kwh": "Expected"})
            chart(px.line(long, x="month", y="kWh", color="Series", markers=True,
                          color_discrete_map={"Observed": "#147d91", "Expected": "#e4a24f"}))
        st.caption("Monthly sums of eligible hourly values; inspect exact hourly deviations below.")
    with right:
        st.markdown("#### Exclusive exclusion reasons")
        reasons = eligibility.loc[~eligibility["eligible"], "exclusion_reason"].value_counts().reset_index()
        reasons.columns = ["Reason", "Hours"]
        if reasons.empty:
            st.info("No excluded observed hours in this selected period.")
        else:
            chart(px.bar(reasons, x="Reason", y="Hours", color_discrete_sequence=["#e4a24f"]))
        st.caption("Excluded hours are not treated as normal or healthy rule evaluations.")
    st.markdown("#### Candidate-hour detail")
    st.caption("Absolute excess and percentage deviation are calculated only where expected kWh is available.")
    detail = candidate.sort_values("hour_start_local", ascending=False)
    st.dataframe(detail, width="stretch", hide_index=True, height=310)
    download("Download selected candidate hours CSV", detail, "energyops_candidate_hours_selected.csv")
    st.markdown("#### Sustained investigation register")
    st.caption("The rule selector changes this incident register only. Incident grain is one sustained group per rule.")
    register = incident_view.sort_values("start_hour_local", ascending=False)
    st.dataframe(register, width="stretch", hide_index=True, height=270)
    download("Download selected incidents CSV", register, "energyops_incidents_selected.csv")

with tabs[3]:
    st.subheader(f"Power-factor review · {period_label}")
    st.caption("Candidate: mean of four 15-minute lagging PF percentages below 70%, "
               "with at least 20 kWh observed. Sustained means two consecutive qualifying hours for the same rule.")
    for column, (label, value) in zip(st.columns(3), [
        ("PF-positive hours", metrics["pf_positive_hours"]),
        ("Sustained PF incidents", metrics["pf_incidents"]),
        ("Combined-priority hours", metrics["combined_priority_hours"]),
    ]):
        column.metric(label, f"{value:,}")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Descriptive mean lagging PF · %")
        pf_daily = hourly.assign(day=hourly["hour_start_local"].dt.normalize()).groupby(
            "day", as_index=False)["mean_lagging_power_factor_pct"].mean()
        chart(px.line(pf_daily, x="day", y="mean_lagging_power_factor_pct",
                      labels={"day": "Date", "mean_lagging_power_factor_pct": "Mean PF %"},
                      color_discrete_sequence=["#147d91"]))
        st.caption("Unweighted mean of four-reading hourly means; descriptive, not a billing aggregate.")
    with right:
        st.markdown("#### Lagging reactive energy · kVarh")
        reactive = daily.assign(month=daily["reading_date"].dt.to_period("M").dt.to_timestamp())
        reactive = reactive.groupby("month", as_index=False)["total_lagging_reactive_power_kvarh"].sum()
        chart(px.bar(reactive, x="month", y="total_lagging_reactive_power_kvarh",
                     labels={"month": "Month", "total_lagging_reactive_power_kvarh": "kVarh"},
                     color_discrete_sequence=["#e4a24f"]))
    st.markdown("#### Source load-class PF context")
    weighted = weighted_pf_by_load(load_view)
    if weighted.empty:
        st.info("Select a load class to show this chart.")
    else:
        chart(px.bar(weighted, x="load_type", y="mean_pf_pct", color="load_type",
                     hover_data=["intervals"],
                     labels={"load_type": "Source load class", "mean_pf_pct": "Interval-weighted mean PF %"},
                     color_discrete_sequence=["#0f718c", "#4caba9", "#e6ac54"]), height=300)
    st.caption("Load-class PF combines daily means weighted by source interval counts; it is not summed.")
    pf_register = incidents[incidents["rule_type"] == "lagging_power_factor_review"].copy()
    st.markdown("#### Power-factor investigation register")
    st.dataframe(pf_register.sort_values("start_hour_local", ascending=False),
                 width="stretch", hide_index=True)

with tabs[4]:
    st.subheader("Actual Apache Superset 3.0 dashboards")
    st.caption("Captured from the verified local SQL dashboard layer. These are static evidence images; "
               "the public app does not connect to local Superset.")
    for title, filename, caption in [
        ("Energy Operations Overview", "energy_operations_dashboard.png", "Usage, intervals, hours and daily patterns"),
        ("Deviation & Incident Investigation", "deviation_investigation_dashboard.png", "Eligibility and candidate review"),
        ("Power-Factor Review", "power_factor_review_dashboard.png", "Power-factor candidates and context"),
        ("Eligibility detail", "eligibility_detail.png", "Excluded warm-up hours retain NULL expected usage"),
    ]:
        with st.expander(title, expanded=title == "Energy Operations Overview"):
            image = ROOT / "evidence" / filename
            if image.exists():
                st.image(str(image), caption=caption, width="stretch")
            else:
                st.warning(f"Verified screenshot unavailable: {filename}")

with tabs[5]:
    st.subheader("Data definitions and provenance")
    st.markdown("""
**Coverage** = observed 15-minute intervals ÷ expected intervals. **Eligibility** requires four current
readings, supported comparable history for every observed load-type component, and non-NULL required values.
The baseline uses prior 28 days, matching load type, clock hour, and weekday/weekend status; see the repository's
baseline documentation for the sample gate and exact formula. An excluded hour has no expected kWh.

**Distinct candidate hours** count observed hours meeting at least one rule once. **Sustained incidents** count
consecutive groups separately by rule; 238 consumption groups plus 5 PF groups are 243 rule-specific incidents.
An hour may meet both rules. PF percentages are descriptive and never summed. kWh and kVarh are additive.

The dataset is historical **2018**, with facility-local timestamps and **unspecified timezone**. Source CO₂
units remain unresolved, so CO₂ is excluded from this presentation. The rules are candidate investigation
heuristics, not confirmed plant operating limits, faults, waste or savings. No live monitoring or external
EnergyOps alert delivery is claimed.
""")
    st.write("Snapshot version:", manifest["snapshot_version"])
    st.write("Generated at (UTC):", manifest["generated_at_utc"])
    st.write("Source CSV SHA-256:", manifest["source_csv_sha256"])
    st.dataframe(pd.DataFrame([{"Dataset": name, "Rows": info["rows"],
                               "Compressed bytes": info["bytes"], "Source view": info["source_view"]}
                              for name, info in manifest["files"].items()]),
                 hide_index=True, width="stretch")
    download("Download selected hourly energy CSV", hourly, "energyops_hourly_selected.csv")
    download("Download selected eligibility CSV", eligibility, "energyops_eligibility_selected.csv")

st.caption("EnergyOps public snapshot · generated from verified PostgreSQL analytics views; "
           "local scheduled EnergyOps alert delivery is planned.")

