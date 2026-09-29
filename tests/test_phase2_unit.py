from collections import Counter
from decimal import Decimal

import pytest

from energyops.database import DatabaseConfig
from energyops.ingestion import already_loaded, convert_row, ingest_csv
from energyops.reconciliation import compare_summaries
from energyops.source_validation import COLUMN_MAP


def valid_row():
    return dict(zip(COLUMN_MAP, ["01/01/2018 00:15", "3.17", "2.95", "0", "0",
                                 "73.21", "100", "900", "Weekday", "Monday", "Light_Load"]))


def test_database_configuration_validation(monkeypatch):
    for key in ("ENERGYOPS_DB_NAME", "ENERGYOPS_DB_USER", "ENERGYOPS_DB_PASSWORD",
                "ENERGYOPS_DB_HOST", "ENERGYOPS_DB_PORT"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError, match="Missing database environment"):
        DatabaseConfig.from_environment(env_file=False)
    for key, value in {"ENERGYOPS_DB_NAME": "energyops", "ENERGYOPS_DB_USER": "app",
                       "ENERGYOPS_DB_PASSWORD": "test-only", "ENERGYOPS_DB_HOST": "127.0.0.1",
                       "ENERGYOPS_DB_PORT": "oops"}.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match="integer"):
        DatabaseConfig.from_environment(env_file=False)
    monkeypatch.setenv("ENERGYOPS_DB_PORT", "5434")
    assert DatabaseConfig.from_environment(env_file=False).port == 5434


def test_canonical_timestamp_and_valid_conversion():
    converted, reasons = convert_row(valid_row())
    assert reasons == []
    assert converted[0].isoformat() == "2018-01-01T00:15:00"
    assert converted[1] == Decimal("3.17")
    assert converted[-1] == "Light_Load"


def test_invalid_row_has_multiple_reasons():
    row = valid_row()
    row.update({"date": "bad", "Usage_kWh": "-1", "NSM": "86400",
                "Load_Type": "Invalid", "Leading_Current_Power_Factor": "101"})
    converted, reasons = convert_row(row)
    assert converted is None
    assert "invalid_timestamp" in reasons
    assert "negative:Usage_kWh" in reasons
    assert "nsm_out_of_range" in reasons
    assert "invalid_category:Load_Type" in reasons
    assert "power_factor_out_of_range:Leading_Current_Power_Factor" in reasons


def test_checksum_blocks_ingestion_before_database_access(tmp_path):
    path = tmp_path / "tiny.csv"
    path.write_text("data", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum differs"):
        ingest_csv(None, path, "0" * 64)


def test_duplicate_source_detection_uses_completed_run():
    class Cursor:
        def fetchone(self):
            return (True,)

    class Connection:
        def execute(self, statement, params):
            assert "run_status = 'completed'" in statement
            assert params == ("a" * 64,)
            return Cursor()

    assert already_loaded(Connection(), "a" * 64)


def test_reconciliation_comparison():
    source = {"rows": 1, "sums": {"usage_kwh": Decimal("1.000000"),
              "lagging_reactive_power_kvarh": Decimal("2"),
              "leading_reactive_power_kvarh": Decimal("3")},
              "categories": {"load_type": Counter({"Light_Load": 1})}}
    database = {"rows": 1, "sums": {"usage_kwh": Decimal("1.0000005"),
                "lagging_reactive_power_kvarh": Decimal("2"),
                "leading_reactive_power_kvarh": Decimal("3")},
                "categories": {"load_type": {"Light_Load": 1}}}
    assert compare_summaries(source, database) == []
    database["sums"]["usage_kwh"] = Decimal("1.1")
    assert compare_summaries(source, database) == ["usage_kwh sum"]
