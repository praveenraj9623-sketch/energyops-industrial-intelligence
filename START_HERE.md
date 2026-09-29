# Reproduce EnergyOps and its public presentation

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

For Phase 3, keep the existing PostgreSQL volume and run the analytics views and checks:

```powershell
python scripts/apply_phase3_models.py
python scripts/apply_phase3_models.py
$env:ENERGYOPS_RUN_DB_TESTS='1'
python -m pytest -q
Remove-Item Env:ENERGYOPS_RUN_DB_TESTS
python scripts/verify_phase1.py
python scripts/verify_phase2.py
python scripts/verify_phase3.py
git diff --check
```

The Phase 3 tests use a separate temporary database. [SQL_MODELS.md](docs/SQL_MODELS.md) defines each view, equation, grain and interpretation limit. The verifier captures `EXPLAIN ANALYZE` observations and writes `evidence/phase3_reconciliation.json`.

For Phase 4, preserve the existing Docker volume and run:

```powershell
python scripts/apply_phase4_models.py
python scripts/apply_phase4_models.py
$env:ENERGYOPS_RUN_DB_TESTS='1'
python -m pytest -q
Remove-Item Env:ENERGYOPS_RUN_DB_TESTS
python scripts/verify_phase1.py
python scripts/verify_phase2.py
python scripts/verify_phase3.py
python scripts/verify_phase4.py
git diff --check
```

Phase 4 fixture tests use another temporary database and leave the real 35,040-row dataset intact. [BASELINE_AND_ELIGIBILITY.md](docs/BASELINE_AND_ELIGIBILITY.md) explains the fixed window, sample gate, exclusions and performance measurements.

For Phase 5, keep the existing PostgreSQL volume and run:

```powershell
python scripts/apply_phase5_models.py
python scripts/apply_phase5_models.py
$env:ENERGYOPS_RUN_DB_TESTS='1'
python -m pytest -q
Remove-Item Env:ENERGYOPS_RUN_DB_TESTS
python scripts/verify_phase1.py
python scripts/verify_phase2.py
python scripts/verify_phase3.py
python scripts/verify_phase4.py
python scripts/verify_phase5.py
git diff --check
```

The Phase 5 fixtures use a temporary database. [INVESTIGATION_RULES.md](docs/INVESTIGATION_RULES.md) records fixed thresholds, actual counts, example historical candidate incidents and interpretation limits. `verify_phase5.py` performs source-backed checks and saves `evidence/phase5_rule_audit.json`.

For Phase 6, keep the existing EnergyOps PostgreSQL volume and configure the additional ignored `.env` fields shown in `.env.example`. Use a unique local Superset secret key, administrator password, metadata password, and analytics-role password. Ensure localhost port 8090 is free. Then run:

```powershell
python -m pip install -r requirements-dev.txt
docker compose up -d
docker compose ps
python scripts/setup_analytics_role.py
python scripts/setup_superset.py
python scripts/setup_superset.py
python scripts/verify_superset.py
$env:ENERGYOPS_RUN_DB_TESTS='1'
python -m pytest -q
Remove-Item Env:ENERGYOPS_RUN_DB_TESTS
python scripts/verify_phase1.py
python scripts/verify_phase2.py
python scripts/verify_phase3.py
python scripts/verify_phase4.py
python scripts/verify_phase5.py
git diff --check
```

Open the local [Superset home](http://127.0.0.1:8090) with the administrator set in `.env`. The [Superset guide](docs/SUPERSET.md) gives dashboard links, filters, screenshots, verification, and volume-preserving restart commands. Phase 6 has 11 datasets, 28 charts and three dashboards. Alert delivery and public hosting remain future work.

For the public Streamlit presentation, first export a verified snapshot on the machine with the EnergyOps database, then run the app locally without database access:

```powershell
python scripts/export_public_snapshot.py
python scripts/verify_public_snapshot.py
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8503
```

Open [http://127.0.0.1:8503](http://127.0.0.1:8503). The intended Cloud URL is [praveen-energyops.streamlit.app](https://praveen-energyops.streamlit.app/); it is not verified as deployed by this local work. Commit `app.py`, `src/energyops/public_snapshot.py`, `data/export/*.csv.gz`, `data/export/manifest.json`, `.streamlit/config.toml`, `evidence/*.png`, and requirements after review, then set `app.py` as the Streamlit Cloud entry point. Do not commit `.env`, the raw CSV, Docker volumes, or Superset metadata. [PUBLIC_PRESENTATION.md](docs/PUBLIC_PRESENTATION.md) records snapshot grains, filter meaning, tests and deployment steps. Local scheduled EnergyOps alert delivery remains planned.

If the CSV is elsewhere, pass `--source path\to\Steel_industry_data.csv` to both scripts or set `ENERGYOPS_SOURCE_CSV` in the environment. `--archive` is optional; omitting it records no ZIP checksum in a regenerated profile. The archived ZIP is never needed for validation. `verify_phase1.py` compares the CSV fingerprint with the saved profile and checks the Phase 1 quality gates.
