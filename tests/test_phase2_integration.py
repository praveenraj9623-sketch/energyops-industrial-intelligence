"""Run with ENERGYOPS_RUN_DB_TESTS=1; uses and removes a dedicated temporary database."""

import csv
import os
import uuid
from datetime import datetime

import psycopg
import pytest
from psycopg import sql

from energyops.database import DatabaseConfig, initialize_database
from energyops.ingestion import ingest_csv
from energyops.provenance import sha256_file
from energyops.source_validation import COLUMN_MAP

pytestmark = pytest.mark.skipif(os.environ.get("ENERGYOPS_RUN_DB_TESTS") != "1",
                                reason="set ENERGYOPS_RUN_DB_TESTS=1 for container integration tests")


def row(stamp="01/01/2018 00:15", usage="3.17"):
    parsed = datetime.strptime(stamp, "%d/%m/%Y %H:%M")
    nsm = parsed.hour * 3600 + parsed.minute * 60
    return dict(zip(COLUMN_MAP, [stamp, usage, "2.95", "0", "0", "73.21", "100",
                                 str(nsm),
                                 "Weekday", "Monday", "Light_Load"]))


def csv_fixture(tmp_path, rows):
    path = tmp_path / (uuid.uuid4().hex + ".csv")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMN_MAP)
        writer.writeheader()
        writer.writerows(rows)
    return path


@pytest.fixture(scope="module")
def test_db():
    config = DatabaseConfig.from_environment()
    name = "energyops_test_" + uuid.uuid4().hex[:12]
    with config.connect() as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    try:
        with config.for_database(name).connect() as conn:
            initialize_database(conn)
            initialize_database(conn)  # rerunnable DDL
            yield conn
    finally:
        with config.connect() as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))


def test_schema_constraints_ingestion_idempotency_and_staging(test_db, tmp_path):
    conn = test_db
    schemas = {r[0] for r in conn.execute("SELECT schema_name FROM information_schema.schemata")}
    assert schemas.issuperset({"raw", "staging", "analytics", "monitoring"})
    path = csv_fixture(tmp_path, [row(), row("01/01/2018 00:30", "-1")])
    first = ingest_csv(conn, path, sha256_file(path), 2)
    assert first["accepted_rows"] == 1 and first["rejected_rows"] == 1
    assert conn.execute("SELECT count(*) FROM raw.steel_energy_rejections").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM raw.steel_energy_readings").fetchone()[0] == 1
    second = ingest_csv(conn, path, sha256_file(path), 2)
    assert second["run_status"] == "skipped_duplicate" and second["inserted_rows"] == 0
    flags = conn.execute("SELECT day_name_matches, week_status_matches, seconds_from_midnight_matches FROM staging.stg_energy_readings").fetchone()
    assert flags == (True, True, True)
    with pytest.raises(ValueError, match="rollback fixture"):
        with conn.transaction():
            conn.execute("UPDATE raw.steel_energy_readings SET day_of_week='Tuesday'")
            assert conn.execute("SELECT day_name_matches FROM staging.stg_energy_readings").fetchone()[0] is False
            raise ValueError("rollback fixture")
    with pytest.raises(psycopg.errors.CheckViolation):
        with conn.transaction():
            conn.execute("UPDATE raw.steel_energy_readings SET usage_kwh=-1")


def test_rollback_on_failed_reconciliation(test_db, tmp_path):
    conn = test_db
    path = csv_fixture(tmp_path, [row("01/01/2018 00:45")])
    with pytest.raises(ValueError, match="row count"):
        ingest_csv(conn, path, sha256_file(path), 2)
    assert conn.execute("SELECT count(*) FROM raw.steel_energy_readings").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM monitoring.ingestion_runs WHERE run_status='failed'").fetchone()[0] == 1
