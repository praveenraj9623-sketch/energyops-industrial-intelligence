"""Local PostgreSQL configuration and repeatable schema initialization."""

import os
from dataclasses import dataclass, replace

import psycopg
from dotenv import load_dotenv

from .config import PROJECT_ROOT

SQL_FILES = [f"{number:02d}_{name}.sql" for number, name in enumerate((
    "schemas", "monitoring_tables", "raw_tables", "staging", "indexes", "permissions"))]


@dataclass(frozen=True)
class DatabaseConfig:
    dbname: str
    user: str
    password: str
    host: str
    port: int

    @classmethod
    def from_environment(cls, *, env_file=True):
        if env_file:
            load_dotenv(PROJECT_ROOT / ".env", override=False)
        names = {"dbname": "ENERGYOPS_DB_NAME", "user": "ENERGYOPS_DB_USER",
                 "password": "ENERGYOPS_DB_PASSWORD", "host": "ENERGYOPS_DB_HOST",
                 "port": "ENERGYOPS_DB_PORT"}
        values = {key: os.environ.get(name, "").strip() for key, name in names.items()}
        missing = [names[key] for key, value in values.items() if not value]
        if missing:
            raise ValueError("Missing database environment variables: " + ", ".join(missing))
        try:
            values["port"] = int(values["port"])
        except ValueError as exc:
            raise ValueError("ENERGYOPS_DB_PORT must be an integer") from exc
        if not 1 <= values["port"] <= 65535:
            raise ValueError("ENERGYOPS_DB_PORT must be between 1 and 65535")
        if values["password"] == "replace-with-a-generated-local-password":
            raise ValueError("Set a generated local ENERGYOPS_DB_PASSWORD in ignored .env")
        return cls(**values)

    def for_database(self, name: str):
        return replace(self, dbname=name)

    def connect(self, **kwargs):
        kwargs.setdefault("autocommit", True)
        return psycopg.connect(dbname=self.dbname, user=self.user, password=self.password,
                               host=self.host, port=self.port, **kwargs)


def initialize_database(conn) -> None:
    with conn.transaction():
        for filename in SQL_FILES:
            statement = (PROJECT_ROOT / "sql" / filename).read_text(encoding="utf-8")
            conn.execute(statement)
