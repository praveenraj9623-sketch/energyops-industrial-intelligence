"""Source contract and reproducible source profiling. No rows are changed."""

from pathlib import Path

import numpy as np
import pandas as pd

from .provenance import file_identity

COLUMN_MAP = {
    "date": "source_timestamp_local",
    "Usage_kWh": "usage_kwh",
    "Lagging_Current_Reactive.Power_kVarh": "lagging_reactive_power_kvarh",
    "Leading_Current_Reactive_Power_kVarh": "leading_reactive_power_kvarh",
    "CO2(tCO2)": "co2_value",
    "Lagging_Current_Power_Factor": "lagging_power_factor_pct",
    "Leading_Current_Power_Factor": "leading_power_factor_pct",
    "NSM": "seconds_from_midnight",
    "WeekStatus": "week_status",
    "Day_of_week": "day_of_week",
    "Load_Type": "load_type",
}
NUMERIC_COLUMNS = list(COLUMN_MAP)[1:8]
POWER_FACTOR_COLUMNS = ["Lagging_Current_Power_Factor", "Leading_Current_Power_Factor"]
ALLOWED = {
    "WeekStatus": {"Weekday", "Weekend"},
    "Day_of_week": {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"},
    "Load_Type": {"Light_Load", "Medium_Load", "Maximum_Load"},
}
TIMESTAMP_FORMAT = "%d/%m/%Y %H:%M"


def validate_columns(columns) -> None:
    actual = list(columns)
    expected = list(COLUMN_MAP)
    if actual != expected:
        raise ValueError(
            f"Source columns differ from contract. Missing: {sorted(set(expected)-set(actual))}; "
            f"unexpected: {sorted(set(actual)-set(expected))}; order matches: {actual == expected}"
        )


def parse_timestamps(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, format=TIMESTAMP_FORMAT, errors="coerce")


def invalid_categories(frame: pd.DataFrame) -> dict[str, dict[str, int]]:
    return {
        name: {str(k): int(v) for k, v in
               frame.loc[frame[name].notna() & ~frame[name].isin(allowed), name]
               .value_counts(dropna=False).items()}
        for name, allowed in ALLOWED.items()
    }


def numeric_issues(frame: pd.DataFrame) -> dict[str, dict[str, int | float | None]]:
    result = {}
    for name in NUMERIC_COLUMNS:
        values = pd.to_numeric(frame[name], errors="coerce")
        finite = values[np.isfinite(values)]
        result[name] = {
            "non_numeric_count": int((frame[name].notna() & values.isna()).sum()),
            "infinite_count": int(np.isinf(values).sum()),
            "negative_count": int((values < 0).sum()),
            "minimum": float(finite.min()) if len(finite) else None,
            "maximum": float(finite.max()) if len(finite) else None,
        }
        if name in POWER_FACTOR_COLUMNS:
            result[name]["outside_0_100_count"] = int(((values < 0) | (values > 100)).sum())
        if name == "NSM":
            result[name]["outside_0_86399_count"] = int(((values < 0) | (values >= 86400)).sum())
            result[name]["non_integer_count"] = int((values.notna() & (values % 1 != 0)).sum())
    return result


def profile_csv(path: str | Path, archive_path: str | Path | None = None) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Source CSV not found: {path}")
    frame = pd.read_csv(path, dtype=str, encoding="utf-8-sig", low_memory=False)
    validate_columns(frame.columns)
    frame = frame.apply(lambda col: col.str.strip())
    frame = frame.replace("", pd.NA)
    timestamps = parse_timestamps(frame["date"])
    valid = timestamps.dropna()
    unique = pd.DatetimeIndex(valid.unique()).sort_values()
    expected = (pd.date_range(unique.min().ceil("15min"), unique.max().floor("15min"), freq="15min")
                if len(unique) else pd.DatetimeIndex([]))
    missing_intervals = expected.difference(unique)
    off_grid = unique.difference(expected)
    counts = valid.value_counts()
    numeric = numeric_issues(frame)
    categories = invalid_categories(frame)
    inferred = {name: ("datetime64[ns]" if name == "date" else
                       "int64" if name == "NSM" and numeric[name]["non_numeric_count"] == 0
                       and numeric[name]["non_integer_count"] == 0 else
                       "float64" if name in NUMERIC_COLUMNS else "string")
                for name in frame.columns}
    observed_days = valid.dt.day_name()
    declared_days = frame["Day_of_week"]
    declared_status = frame["WeekStatus"]
    expected_status = observed_days.map(lambda day: "Weekend" if day in {"Saturday", "Sunday"} else "Weekday")
    nsm = pd.to_numeric(frame["NSM"], errors="coerce")
    expected_nsm = timestamps.dt.hour * 3600 + timestamps.dt.minute * 60

    profile = {
        "source": file_identity(path),
        "archive": file_identity(archive_path) if archive_path and Path(archive_path).is_file() else None,
        "row_count": len(frame), "column_count": len(frame.columns),
        "columns": list(frame.columns), "canonical_columns": COLUMN_MAP,
        "inferred_types": inferred,
        "timestamp": {
            "format": TIMESTAMP_FORMAT, "minimum": valid.min().isoformat() if len(valid) else None,
            "maximum": valid.max().isoformat() if len(valid) else None,
            "parse_success_count": int(timestamps.notna().sum()),
            "parse_failure_count": int(timestamps.isna().sum()),
            "expected_frequency_minutes": 15,
        },
        "duplicate_complete_rows": int(frame.duplicated().sum()),
        "duplicate_timestamps": int(valid.duplicated().sum()),
        "duplicated_timestamp_groups": int((counts > 1).sum()),
        "missing_values": {k: int(v) for k, v in frame.isna().sum().items()},
        "numeric_checks": numeric,
        "unexpected_categories": categories,
        "intervals": {
            "expected_count_in_coverage": len(expected),
            "unique_observed_count": len(unique),
            "missing_interval_count": len(missing_intervals),
            "off_grid_timestamp_count": len(off_grid),
            "first_missing_intervals": [x.isoformat() for x in missing_intervals[:10]],
            "first_off_grid_timestamps": [x.isoformat() for x in off_grid[:10]],
        },
        "cross_field_checks": {
            "day_of_week_mismatch_count": int((timestamps.notna() & declared_days.ne(observed_days)).sum()),
            "week_status_mismatch_count": int((timestamps.notna() & declared_status.ne(expected_status)).sum()),
            "nsm_timestamp_mismatch_count": int((timestamps.notna() & nsm.notna() & nsm.ne(expected_nsm)).sum()),
        },
        "observations_by_load_type": {str(k): int(v) for k, v in frame["Load_Type"].value_counts(dropna=False).items()},
        "observations_by_week_status": {str(k): int(v) for k, v in frame["WeekStatus"].value_counts(dropna=False).items()},
        "observations_by_day_of_week": {str(k): int(v) for k, v in frame["Day_of_week"].value_counts(dropna=False).items()},
    }
    return profile
