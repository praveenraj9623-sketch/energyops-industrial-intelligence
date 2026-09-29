"""Phase 4 method parameters and SQL view application."""

from .config import PROJECT_ROOT

TRAILING_DAYS = 28
MIN_COMPARABLE_SAMPLES = 12
METHOD_VERSION = "trailing_28d_load_hour_weekstatus_median_v1"
SQL_FILES = ("19_baseline_index.sql", "20_energy_baseline_components.sql", "21_energy_hourly_eligibility.sql",
             "22_energy_eligibility_status.sql")


def apply_baseline_models(conn) -> None:
    with conn.transaction():
        for filename in SQL_FILES:
            conn.execute((PROJECT_ROOT / "sql" / filename).read_text(encoding="utf-8"))
