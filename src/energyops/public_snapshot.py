"""Read and filter the committed, database-free public presentation snapshot."""

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


DATE_COLUMNS = {
    "hourly": ["hour_start_local"],
    "daily": ["reading_date"],
    "daily_by_load_type": ["reading_date"],
    "eligibility": ["hour_start_local"],
    "candidate_hours": ["hour_start_local"],
    "incidents": ["start_hour_local", "last_candidate_hour_local"],
}


def load_snapshot(root: Path):
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["snapshot_version"] != "energyops_public_snapshot_v1":
        raise ValueError("Unsupported public snapshot version")
    tables = {}
    for name, info in manifest["files"].items():
        file = root / info["file"]
        if hashlib.sha256(file.read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError(f"Snapshot checksum mismatch: {name}")
        frame = pd.read_csv(file, compression="gzip", parse_dates=DATE_COLUMNS[name])
        if len(frame) != info["rows"] or list(frame.columns) != info["columns"]:
            raise ValueError(f"Snapshot schema or row-count mismatch: {name}")
        tables[name] = frame
    return manifest, tables


def select_dates(frame: pd.DataFrame, column: str, start: date, end: date):
    """Inclusive facility-local dates; preserve each table's native grain."""
    lower = pd.Timestamp(start)
    upper = pd.Timestamp(end + timedelta(days=1))
    return frame.loc[(frame[column] >= lower) & (frame[column] < upper)].copy()


def period_metrics(hourly: pd.DataFrame, eligibility: pd.DataFrame,
                   candidate_hours: pd.DataFrame, incidents: pd.DataFrame):
    return {
        "usage_kwh": float(hourly["total_usage_kwh"].sum()),
        "intervals": int(hourly["observed_interval_count"].sum()),
        "observed_hours": len(hourly),
        "eligible_hours": int(eligibility["eligible"].sum()),
        "excluded_hours": int((~eligibility["eligible"]).sum()),
        "candidate_hours": len(candidate_hours),
        "consumption_positive_hours": int(eligibility["consumption_deviation_candidate"].sum()),
        "pf_positive_hours": int(eligibility["lagging_power_factor_review_candidate"].sum()),
        "combined_priority_hours": int(eligibility["combined_priority"].sum()),
        "consumption_incidents": int((incidents["rule_type"] == "consumption_deviation").sum()),
        "pf_incidents": int((incidents["rule_type"] == "lagging_power_factor_review").sum()),
    }


def weighted_pf_by_load(frame: pd.DataFrame):
    """Weight descriptive daily load-type PF means by source interval counts."""
    if frame.empty:
        return pd.DataFrame(columns=["load_type", "mean_pf_pct", "intervals"])
    work = frame.assign(weighted_pf=frame["mean_lagging_power_factor_pct"]
                        * frame["observed_interval_count"])
    grouped = work.groupby("load_type", as_index=False).agg(
        weighted_pf=("weighted_pf", "sum"), intervals=("observed_interval_count", "sum"))
    grouped["mean_pf_pct"] = grouped["weighted_pf"] / grouped["intervals"]
    return grouped[["load_type", "mean_pf_pct", "intervals"]]
