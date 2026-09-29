"""Independent source and Python audit of Phase 5 decisions and island grouping."""

import csv
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .baseline_audit import compare_sample, evaluate_source_hour, read_source, TOLERANCE, _plan
from .investigation_rules import RULE_VERSION, apply_investigation_models, decide_hour
from .provenance import sha256_file
from .source_validation import TIMESTAMP_FORMAT, validate_columns


def _source_hours(path):
    grouped = defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        validate_columns(reader.fieldnames)
        for row in reader:
            stamp = datetime.strptime(row["date"], TIMESTAMP_FORMAT)
            grouped[stamp.replace(minute=0)].append((stamp, Decimal(row["Usage_kWh"]),
                                                      Decimal(row["Lagging_Current_Power_Factor"]),
                                                      row["Load_Type"]))
    return grouped


def _islands(positive_hours):
    result = []
    current = []
    for hour in sorted(positive_hours):
        if current and hour != current[-1] + timedelta(hours=1):
            if len(current) >= 2:
                result.append(current)
            current = []
        current.append(hour)
    if len(current) >= 2:
        result.append(current)
    return result


def audit_phase5(conn, path, source_profile):
    problems = []
    grouped = _source_hours(path)
    source_readings = read_source(path)
    checksum = sha256_file(path)
    if checksum != source_profile["source"]["sha256"] or sum(map(len, grouped.values())) != source_profile["row_count"]:
        problems.append("source identity or row count mismatch")
    def snapshot():
        return {"raw": conn.execute("SELECT count(*),sum(usage_kwh) FROM raw.steel_energy_readings").fetchone(),
                "runs": conn.execute("SELECT count(*) FROM monitoring.ingestion_runs").fetchone()[0],
                "summary": conn.execute("SELECT * FROM analytics.energy_rule_summary ORDER BY rule_type").fetchall(),
                "incident_keys": conn.execute("SELECT incident_key FROM analytics.energy_candidate_incidents ORDER BY incident_key").fetchall()}
    before = snapshot()
    apply_investigation_models(conn)
    once = snapshot()
    apply_investigation_models(conn)
    twice = snapshot()
    if before != once or once != twice:
        problems.append("model rerun changed outcomes, raw data or ingestion history")
    cursor = conn.execute("SELECT * FROM analytics.energy_rule_evaluation ORDER BY hour_start_local")
    names = [col.name for col in cursor.description]
    rows = [dict(zip(names, row)) for row in cursor.fetchall()]
    by_hour = {r["hour_start_local"]: r for r in rows}
    if len(rows) != len(by_hour) or set(by_hour) != set(grouped) or len(rows) != 8760:
        problems.append("evaluation grain differs from observed source hours")
    positive = {"consumption_deviation": [], "lagging_power_factor_review": []}
    for hour, raw in grouped.items():
        row = by_hour.get(hour)
        if row is None:
            continue
        usage = sum((r[1] for r in raw), Decimal(0))
        mean_pf = sum((r[2] for r in raw), Decimal(0)) / len(raw)
        decision = decide_hour(row["eligible"], len(raw), usage, row["expected_usage_kwh"], mean_pf)
        if row["current_observation_count"] != len(raw) or abs(row["observed_usage_kwh"] - usage) > TOLERANCE:
            problems.append(f"source usage/count mismatch: {hour}")
        if row["mean_lagging_power_factor_pct"] is None or abs(row["mean_lagging_power_factor_pct"] - mean_pf) > TOLERANCE:
            problems.append(f"source power factor mismatch: {hour}")
        for name in ("consumption_deviation_candidate", "lagging_power_factor_review_candidate", "combined_priority"):
            if row[name] is not decision[name]:
                problems.append(f"Python rule disagreement: {name}: {hour}")
        if row["rule_version"] != RULE_VERSION or not row["eligible"] and any(row[n] for n in (
                "consumption_deviation_candidate", "lagging_power_factor_review_candidate", "combined_priority")):
            problems.append(f"version or excluded flag error: {hour}")
        if decision["consumption_deviation_candidate"]:
            positive["consumption_deviation"].append(hour)
        if decision["lagging_power_factor_review_candidate"]:
            positive["lagging_power_factor_review"].append(hour)
    candidate_rows = conn.execute("SELECT hour_start_local FROM analytics.energy_candidate_hours").fetchall()
    expected_candidate_hours = {h for hours in positive.values() for h in hours}
    if {r[0] for r in candidate_rows} != expected_candidate_hours or len(candidate_rows) != len(expected_candidate_hours):
        problems.append("candidate-hours projection differs from Python decisions")
    incident_rows = conn.execute("""SELECT rule_type,start_hour_local,last_candidate_hour_local,
        observed_hour_count,incident_key,status,peak_observed_usage_kwh,peak_positive_excess_kwh,
        peak_signed_deviation_pct,minimum_mean_lagging_power_factor_pct,hourly_load_type_context
        FROM analytics.energy_candidate_incidents""").fetchall()
    expected_islands = {(rule, group[0], group[-1], len(group))
                        for rule, hours in positive.items() for group in _islands(hours)}
    if {(r[0], r[1], r[2], r[3]) for r in incident_rows} != expected_islands or len(incident_rows) != len(expected_islands):
        problems.append("sustained islands disagree with independent Python grouping")
    if len({r[4] for r in incident_rows}) != len(incident_rows) or any(r[5] != "candidate for review" for r in incident_rows):
        problems.append("incident key or status error")
    for incident in incident_rows:
        rule, start, end, count, key, _, peak_usage, peak_excess, peak_deviation, min_pf, context = incident
        group = [start + timedelta(hours=offset) for offset in range(count)]
        expected_key = hashlib.md5(f"{RULE_VERSION}|{rule}|{start:%Y-%m-%d %H:%M:%S}".encode()).hexdigest()
        if group[-1] != end or key != expected_key or len(context) != count:
            problems.append(f"incident key, length or context mismatch: {rule}: {start}")
            continue
        if any(h not in positive[rule] for h in group):
            problems.append(f"incident includes a non-positive hour: {rule}: {start}")
        member_rows = [by_hour[h] for h in group]
        aggregates = (max(r["observed_usage_kwh"] for r in member_rows),
                      max(max(r["excess_kwh"], Decimal(0)) for r in member_rows),
                      max(r["deviation_pct"] for r in member_rows),
                      min(r["mean_lagging_power_factor_pct"] for r in member_rows))
        if any(abs(actual - expected) > TOLERANCE for actual, expected in zip(
                (peak_usage, peak_excess, peak_deviation, min_pf), aggregates)):
            problems.append(f"incident aggregate mismatch: {rule}: {start}")
        for hour, item in zip(group, context):
            if item["hour_start_local"] != hour.isoformat() or item["load_type_components"] != by_hour[hour]["load_type_component_evidence"]:
                problems.append(f"incident component context mismatch: {rule}: {start}")
    summary_rows = conn.execute("SELECT * FROM analytics.energy_rule_summary ORDER BY rule_type").fetchall()
    for rule, observed, eligible, excluded, candidates, incidents, incident_hours, combined, version in summary_rows:
        groups = _islands(positive[rule])
        if (observed, eligible, excluded, candidates, incidents, incident_hours, version) != (
                len(rows), sum(r["eligible"] for r in rows), sum(not r["eligible"] for r in rows),
                len(positive[rule]), len(groups), sum(map(len, groups)), RULE_VERSION):
            problems.append(f"summary mismatch: {rule}")
        if combined != sum(r["combined_priority"] for r in rows):
            problems.append("combined count mismatch")
    selection = [min(grouped), min(grouped) + timedelta(days=2), datetime(2018, 3, 15, 10),
                 datetime(2018, 3, 17, 10), datetime(2018, 12, 31, 0), max(grouped)]
    for rule in positive:
        if positive[rule]:
            selection.append(positive[rule][0])
        groups = _islands(positive[rule])
        if groups:
            selection.extend((groups[0][0], groups[0][-1]))
    eligible_nonbreach = next((h for h in sorted(by_hour) if by_hour[h]["eligible"]
                               and h not in expected_candidate_hours), None)
    if eligible_nonbreach:
        selection.append(eligible_nonbreach)
    across_midnight = next(((h, h + timedelta(hours=1)) for rule, hours in positive.items()
                            for h in hours if h.hour == 23 and h + timedelta(hours=1) in hours), None)
    if across_midnight:
        selection.extend(across_midnight)
    else:
        problems.append("no across-midnight candidate pair available for requested source audit")
    gap = next(((h, h + timedelta(hours=1), h + timedelta(hours=2))
                for rule, hours in positive.items() for h in hours
                if h + timedelta(hours=2) in hours and h + timedelta(hours=1) not in hours
                and h + timedelta(hours=1) in by_hour), None)
    if gap:
        selection.extend(gap)
    else:
        problems.append("no candidate-gap example available for requested source audit")
    mixed = next((h for h in sorted(grouped) if h >= datetime(2018, 3, 1)
                  and len({r[3] for r in grouped[h]}) > 1), None)
    if mixed:
        selection.append(mixed)
    samples = []
    for hour in dict.fromkeys(selection):
        independent = evaluate_source_hour(source_readings, hour)
        ecur = conn.execute("SELECT * FROM analytics.energy_hourly_baseline_eligibility WHERE hour_start_local=%s", (hour,))
        baseline = dict(zip([c.name for c in ecur.description], ecur.fetchone()))
        diffs = compare_sample(independent, baseline)
        if diffs:
            problems.append(f"independent baseline {hour}: {diffs}")
        samples.append({"hour_start_local": hour.isoformat(), "eligible": independent["eligible"],
                        "load_types": sorted(independent["components"]),
                        "historical_window_start_local": independent["historical_window_start_local"].isoformat(),
                        "historical_window_end_exclusive_local": independent["historical_window_end_exclusive_local"].isoformat(),
                        "historical_sample_count_total": independent["historical_sample_count_total"],
                        "expected_usage_kwh": str(independent["expected_usage_kwh"]) if independent["expected_usage_kwh"] is not None else None,
                        "every_history_timestamp_before_hour": all(c["every_historical_timestamp_before_hour"] for c in independent["components"].values()),
                        "every_history_timestamp_in_window": all(c["every_historical_timestamp_in_window"] for c in independent["components"].values()),
                        "consumption_candidate": by_hour[hour]["consumption_deviation_candidate"],
                        "power_factor_candidate": by_hour[hour]["lagging_power_factor_review_candidate"],
                        "independent_baseline_match": not diffs})
    if len(rows) != 8760 or sum(r["eligible"] for r in rows) != 7762:
        problems.append("Phase 4 eligibility changed")
    if before["raw"] != (35040, Decimal("959636.71")):
        problems.append("raw row count or reconciled kWh changed")
    plans = {"summary_full": _plan(conn, "SELECT * FROM analytics.energy_rule_summary"),
             "incidents_full": _plan(conn, "SELECT * FROM analytics.energy_candidate_incidents"),
             "evaluation_week": _plan(conn, "SELECT hour_start_local,eligible,consumption_deviation_candidate,lagging_power_factor_review_candidate FROM analytics.energy_rule_evaluation WHERE hour_start_local >= TIMESTAMP '2018-06-01' AND hour_start_local < TIMESTAMP '2018-06-08'")}
    return {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "audit_status": "passed" if not problems else "failed",
            "problems": problems, "source_sha256": checksum, "rule_version": RULE_VERSION,
            "thresholds": {"minimum_excess_kwh": "10", "minimum_deviation_pct": "30",
                           "lagging_pf_strictly_below_pct": "70", "minimum_pf_usage_kwh": "20",
                           "minimum_consecutive_hours": 2},
            "observed_hours": len(rows), "eligible_hours": sum(r["eligible"] for r in rows),
            "excluded_hours": sum(not r["eligible"] for r in rows), "candidate_hours_any": len(candidate_rows),
            "combined_priority_hours": sum(r["combined_priority"] for r in rows),
            "rule_summary": [{"rule_type": r[0], "observed_hours": r[1], "eligible_hours": r[2],
                              "excluded_hours": r[3], "positive_hours": r[4], "sustained_incidents": r[5],
                              "sustained_candidate_hours": r[6]} for r in summary_rows],
            "sampled_hours": samples, "all_sampled_history_strictly_earlier": all(s["every_history_timestamp_before_hour"] for s in samples),
            "source_case_hours": {
                "eligible_nonbreaching": eligible_nonbreach.isoformat() if eligible_nonbreach else None,
                "consecutive_across_day_boundary": [h.isoformat() for h in across_midnight] if across_midnight else [],
                "candidate_gap_candidate": [h.isoformat() for h in gap] if gap else [],
                "mixed_load": mixed.isoformat() if mixed else None,
            },
            "rerun_snapshots_equal": before == once == twice, "raw_readings": before["raw"][0],
            "raw_usage_kwh": str(before["raw"][1]), "ingestion_runs": before["runs"],
            "explain_analyze": plans}
