import pandas as pd
import pytest

from energyops.source_validation import (
    ALLOWED, COLUMN_MAP, invalid_categories, numeric_issues, parse_timestamps,
    profile_csv, validate_columns,
)


def row(timestamp="01/01/2018 00:15"):
    return dict(zip(COLUMN_MAP, [timestamp, "3.17", "2.95", "0", "0", "73.21",
                                 "100", "900", "Weekday", "Monday", "Light_Load"]))


def write_csv(tmp_path, rows):
    path = tmp_path / "sample.csv"
    pd.DataFrame(rows, columns=COLUMN_MAP).to_csv(path, index=False)
    return path


def test_exact_schema_and_mapping():
    validate_columns(COLUMN_MAP)
    assert COLUMN_MAP["CO2(tCO2)"] == "co2_value"
    assert COLUMN_MAP["date"] == "source_timestamp_local"
    with pytest.raises(ValueError, match="Missing"):
        validate_columns(list(COLUMN_MAP)[:-1])
    with pytest.raises(ValueError, match="order matches: False"):
        validate_columns(list(COLUMN_MAP)[::-1])


def test_timestamp_parsing_and_invalid_detection():
    parsed = parse_timestamps(pd.Series(["01/01/2018 00:15", "not-a-date", "31/02/2018 00:15"]))
    assert parsed.iloc[0] == pd.Timestamp("2018-01-01 00:15")
    assert parsed.isna().sum() == 2


def test_allowed_categories_and_rejection():
    frame = pd.DataFrame([row(), {**row(), "Load_Type": "Unknown", "WeekStatus": "Holiday",
                                     "Day_of_week": "Moonday"}])
    issues = invalid_categories(frame)
    assert issues == {"WeekStatus": {"Holiday": 1}, "Day_of_week": {"Moonday": 1},
                      "Load_Type": {"Unknown": 1}}
    assert ALLOWED["Load_Type"] == {"Light_Load", "Medium_Load", "Maximum_Load"}


def test_numeric_ranges_and_non_numeric():
    frame = pd.DataFrame([row(), {**row(), "Usage_kWh": "-1", "NSM": "86400",
                                     "Lagging_Current_Power_Factor": "101",
                                     "Leading_Current_Power_Factor": "inf"},
                          {**row(), "Usage_kWh": "oops"}])
    issues = numeric_issues(frame)
    assert issues["Usage_kWh"]["negative_count"] == 1
    assert issues["Usage_kWh"]["non_numeric_count"] == 1
    assert issues["NSM"]["outside_0_86399_count"] == 1
    assert issues["Lagging_Current_Power_Factor"]["outside_0_100_count"] == 1
    assert issues["Leading_Current_Power_Factor"]["infinite_count"] == 1


def test_duplicate_and_gap_detection(tmp_path):
    path = write_csv(tmp_path, [row(), row(), row("01/01/2018 00:45")])
    profile = profile_csv(path)
    assert profile["duplicate_complete_rows"] == 1
    assert profile["duplicate_timestamps"] == 1
    assert profile["intervals"]["missing_interval_count"] == 1


def test_off_grid_timestamp_detection(tmp_path):
    path = write_csv(tmp_path, [row("01/01/2018 00:17")])
    assert profile_csv(path)["intervals"]["off_grid_timestamp_count"] == 1


def test_missing_source_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="Source CSV not found"):
        profile_csv(tmp_path / "absent.csv")
