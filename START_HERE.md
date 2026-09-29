# Reproduce Phases 1 and 2

Use Python 3.11 from the repository root. The dataset is distributed by [UCI under CC BY 4.0](docs/SOURCE_ATTRIBUTION.md); download and extract it yourself. Place `Steel_industry_data.csv` in `data/raw/` (Git ignored). Optionally retain the ZIP outside the repository to record its checksum.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python scripts/profile_source.py --archive 'C:\Users\admin\Downloads\energyops-source\steel-industry-energy-consumption.zip'
python -m pytest -q
python scripts/verify_phase1.py
git check-ignore -v data/raw/Steel_industry_data.csv
git status --short
```

For Phase 2, install Docker Desktop, ensure it is running, and copy `.env.example` to `.env`. Replace the example password with a unique local secret; `.env` is Git ignored. Then run:

```powershell
docker compose up -d
docker compose ps
python scripts/initialize_database.py
python scripts/load_postgres.py
python scripts/load_postgres.py
$env:ENERGYOPS_RUN_DB_TESTS='1'
python -m pytest -q
Remove-Item Env:ENERGYOPS_RUN_DB_TESTS
python scripts/verify_phase2.py
docker compose logs --tail 50 energyops-db
```

The integration tests create and remove a dedicated temporary database; they do not modify the real `energyops` data. See [POSTGRESQL.md](docs/POSTGRESQL.md) for shutdown, volume-preserving restart, the clearly marked destructive reset, and troubleshooting. See [INGESTION.md](docs/INGESTION.md) for audit, quarantine and reconciliation details.

If the CSV is elsewhere, pass `--source path\to\Steel_industry_data.csv` to both scripts or set `ENERGYOPS_SOURCE_CSV` in the environment. `--archive` is optional; omitting it records no ZIP checksum in a regenerated profile. The archived ZIP is never needed for validation. `verify_phase1.py` compares the CSV fingerprint with the saved profile and checks the Phase 1 quality gates.
