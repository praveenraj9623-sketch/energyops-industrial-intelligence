# Local PostgreSQL 16

Docker Compose runs one `postgres:16` service, `energyops-db`, on `127.0.0.1:5434` mapped to container port 5432. Data persists in the dedicated `energyops_pgdata` named volume. This is a reproducible local development and analytics environment, not a hardened production deployment.

Copy `.env.example` to ignored `.env` and set a unique local password. The application reads `ENERGYOPS_DB_NAME`, `ENERGYOPS_DB_USER`, `ENERGYOPS_DB_PASSWORD`, `ENERGYOPS_DB_HOST`, `ENERGYOPS_DB_PORT`; Compose also documents `ENERGYOPS_DB_CONTAINER_PORT` (PostgreSQL listens on 5432 in the container). The default database and owner are `energyops` and `energyops_app`. Do not check `.env` into Git.

```powershell
docker compose up -d
docker compose ps
python scripts/initialize_database.py
python scripts/load_postgres.py
python scripts/load_postgres.py
python scripts/verify_phase2.py
```

Initialization applies rerunnable SQL in `sql/00` through `sql/05`. `raw` contains typed readings and rejected source rows; `monitoring` contains ingestion runs; `staging` contains a read-only view. `analytics` is reserved and empty. The owner creates the objects and PUBLIC schema access is revoked. This is not a separate read-only role model.

The raw grain is one record per facility-local source timestamp for this verified dataset. Unique constraints protect the timestamp and `(source_file_sha256, source_row_number)`. Business fields are non-null, with nonnegative energy values, 0–100 power factors, 0–86399 seconds from midnight and fixed categories. An audit run refers to the exact source checksum. Indexes cover load type, week status, day of week and run ID; timestamp and `(hash,row)` uniqueness provide indexes for timestamp and source hash lookups. An index on the audit table's source hash supports duplicate-run detection. No reading-date expression index is needed for Phase 2.

Use `docker compose down` to stop while keeping the named volume. `docker compose up -d` restarts with persisted data. **Destructive reset:** `docker compose down -v` removes the database volume and all loaded data; use only when you intend to rebuild and reload. If port 5434 is occupied on another machine, choose an unused port in `.env` and use the same port for Python and Compose.

Troubleshooting: check `docker compose ps` for `healthy`, inspect `docker compose logs --tail 50 energyops-db` without sharing secrets, confirm Docker Desktop is running, and ensure the ignored `.env` password matches the password used when the volume was first initialized. Changing the password in `.env` alone does not change an existing volume's database credentials.
