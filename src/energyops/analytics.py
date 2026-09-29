"""Rerunnable Phase 3 analytics views; raw ingestion remains untouched."""

from .config import PROJECT_ROOT

MODEL_FILES = (
    "10_energy_hourly.sql",
    "11_energy_daily.sql",
    "12_energy_by_load_type.sql",
    "13_energy_profiles.sql",
)
MODEL_NAMES = (
    "energy_hourly", "energy_daily", "energy_hourly_by_load_type",
    "energy_daily_by_load_type", "energy_hour_of_day_profile",
    "energy_load_type_summary",
)


def apply_analytics_models(conn) -> None:
    with conn.transaction():
        for filename in MODEL_FILES:
            conn.execute((PROJECT_ROOT / "sql" / filename).read_text(encoding="utf-8"))
