"""Create or refresh the least-privilege Superset data-source login."""

import os
import sys
from pathlib import Path

from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energyops.database import DatabaseConfig  # noqa: E402

VIEWS = (
    "energy_hourly", "energy_daily", "energy_hourly_by_load_type",
    "energy_daily_by_load_type", "energy_hour_of_day_profile",
    "energy_load_type_summary", "energy_hourly_baseline_eligibility",
    "energy_hourly_eligibility_status", "energy_rule_evaluation",
    "energy_candidate_hours", "energy_candidate_incidents", "energy_rule_summary",
)


def main():
    config = DatabaseConfig.from_environment()
    user = os.environ.get("ENERGYOPS_ANALYTICS_USER", "energyops_analytics_ro")
    password = os.environ.get("ENERGYOPS_ANALYTICS_PASSWORD")
    if not password or password.startswith("replace-with-"):
        raise SystemExit("Set a generated ENERGYOPS_ANALYTICS_PASSWORD in ignored .env")
    identifier = sql.Identifier(user)
    with config.connect() as conn:
        with conn.transaction():
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (user,)).fetchone()
            if exists:
                conn.execute(sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    identifier, sql.Literal(password)))
            else:
                conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    identifier, sql.Literal(password)))
            conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(config.dbname), identifier))
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA analytics TO {}").format(identifier))
            for view in VIEWS:
                conn.execute(sql.SQL("GRANT SELECT ON analytics.{} TO {}").format(
                    sql.Identifier(view), identifier))
            conn.execute(sql.SQL("ALTER ROLE {} SET default_transaction_read_only = on").format(identifier))
    print(f"Configured read-only analytics role for {len(VIEWS)} explicit views.")


if __name__ == "__main__":
    main()
