# Public Streamlit presentation

The intended Streamlit Cloud URL is [praveen-energyops.streamlit.app](https://praveen-energyops.streamlit.app/). The repository provides a deployable `app.py`; local verification does not establish that the public URL has been deployed. Apache Superset 3.0 remains the primary local SQL dashboard layer. Streamlit is a read-only public presentation of a committed 2018 snapshot and the actual Superset screenshots.

## Snapshot contract

Run `python scripts/export_public_snapshot.py` from a machine with the verified EnergyOps PostgreSQL database and ignored `.env`. The exporter reads only the existing `analytics` views inside a repeatable-read, read-only transaction. It writes stable-order gzip CSV files with a zero gzip timestamp to `data/export/`; the manifest records generation time, source SHA-256, table row counts, compressed byte sizes, file checksums, snapshot version and full-year reconciled metrics. The exporter refuses mismatches against Phase 3–6 evidence. Reapplying the export leaves compressed table bytes identical when source views are unchanged; the manifest generation timestamp advances.

| File | Grain | Rows in verified export |
|---|---|---:|
| `hourly.csv.gz` | One observed facility-local hour | 8,760 |
| `daily.csv.gz` | One observed facility-local date | 365 |
| `daily_by_load_type.csv.gz` | One date and source load class | 971 |
| `eligibility.csv.gz` | One observed hour, with NULL expectation for excluded hours | 8,760 |
| `candidate_hours.csv.gz` | One distinct condition-positive hour | 1,343 |
| `incidents.csv.gz` | One sustained rule-specific incident | 243 |

The six compressed files total **374,347 bytes** in the verified export. They contain no raw CSV rows, credentials or Superset metadata. The app checks each file's checksum, schema and row count before rendering. It uses only these files and the committed `evidence/*.png` images at runtime; it does not contact PostgreSQL, Docker, Superset or another network service.

## Run locally

```powershell
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8503
```

Open [http://127.0.0.1:8503](http://127.0.0.1:8503). No `.env`, database or Docker service is needed to run this command. The root `.streamlit/config.toml` contains only non-secret appearance settings.

## Deploy to Streamlit Community Cloud

After reviewing and committing the repository yourself, select this GitHub repository and branch in Streamlit Community Cloud, choose `app.py` as the entry point, and select Python 3.11 in advanced settings. The root `requirements.txt` supplies Streamlit, pandas and Plotly; Streamlit documents this [repository layout](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/file-organization) and [dependency file](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies). The snapshot CSV files, `manifest.json`, and four Superset images under `evidence/` must be included in the commit; `.env`, `data/raw/`, PostgreSQL volumes and Superset metadata must remain excluded. No Cloud secrets or database connection are required. The app does not publish or refresh the snapshot automatically; export, verify, review, commit and redeploy a new snapshot deliberately.

## Filter meaning

The inclusive date selector filters each exported table on its facility-local date. The four fixed benchmark cards and six secondary benchmark values always refer to the full 2018 year. Selected-period cards are labeled separately. The load-class selector only changes daily source-load charts and the descriptive interval-weighted PF-by-load chart; an hour can contain multiple source classes. The incident rule selector only changes the rule-specific incident register. Incident dates use the first qualifying hour. Distinct candidate-hour counts use the separate hour-grain table and cannot be added to the 243 rule-specific sustained incidents.

Energy and reactive energy are additive. Coverage divides selected observed intervals by selected expected intervals. The PF load comparison weights daily descriptive means by their source interval counts; no PF percentage is summed. The baseline and rule details remain in [BASELINE_AND_ELIGIBILITY.md](BASELINE_AND_ELIGIBILITY.md) and [INVESTIGATION_RULES.md](INVESTIGATION_RULES.md). The 2018 timestamps have unspecified timezone. CO₂ source units remain unresolved. These are candidate investigations, not live monitoring, confirmed faults, savings or delivered alerts. Local scheduled EnergyOps alert delivery is planned separately.

## Verification

```powershell
python scripts/export_public_snapshot.py
python scripts/verify_public_snapshot.py
$env:ENERGYOPS_RUN_DB_TESTS='1'
python -m pytest -q
Remove-Item Env:ENERGYOPS_RUN_DB_TESTS
python scripts/verify_phase1.py
python scripts/verify_phase2.py
python scripts/verify_phase3.py
python scripts/verify_phase4.py
python scripts/verify_phase5.py
python scripts/verify_superset.py
git diff --check
git check-ignore -v .env data/raw/Steel_industry_data.csv
git status --short
```

The four Superset captures are [operations](../evidence/energy_operations_dashboard.png), [investigation](../evidence/deviation_investigation_dashboard.png), [PF review](../evidence/power_factor_review_dashboard.png), and [eligibility](../evidence/eligibility_detail.png). The [local Streamlit preview](../evidence/streamlit_public_preview.png) is additional rendering evidence.
