# Local Superset analytics (Phase 6)

EnergyOps runs Apache Superset 3.0.0 at [http://127.0.0.1:8090](http://127.0.0.1:8090). This is a local Docker Compose installation over historical 2018 data. It does not deliver alerts or expose a public site. Superset queries the verified, nonmaterialized PostgreSQL `analytics` views; it holds no copy of the 35,040 raw readings.

## Start and reproduce

Use Python 3.11, Docker Desktop, and the repository root. Preserve the existing `energyops_pgdata` volume. Install `requirements-dev.txt`; put unique local values for every password and `SUPERSET_SECRET_KEY` in the Git-ignored `.env` using `.env.example` as the field list. Keep the existing EnergyOps database settings and source CSV. Port 8090 must be free. Run:

```powershell
python -m pip install -r requirements-dev.txt
docker compose up -d
docker compose ps
python scripts/setup_analytics_role.py
python scripts/setup_superset.py
python scripts/setup_superset.py
python scripts/verify_superset.py
```

The first setup run applies Superset metadata migrations, creates the local administrator if missing, initializes security, and registers the database and assets. The second run updates assets by stable name. It produced the same **11 datasets, 28 charts, and 3 dashboards** without duplicates. The metadata PostgreSQL and Superset home use separate named volumes, `energyops_superset_metadata` and `energyops_superset_home`. A volume-preserving stop/start of both Superset services retained all assets and passed the full Superset audit. Restart without removing volumes:

```powershell
docker compose stop
docker compose up -d
docker compose ps
python scripts/verify_superset.py
```

The connection uses `energyops_analytics_ro`, not the EnergyOps owner. `setup_analytics_role.py` grants `USAGE` on `analytics`, `SELECT` on the 11 named dashboard views plus the eligibility status view, and enforces read-only transactions. The verifier confirms the role can read 8,760 hourly rows and cannot select from `raw`, insert into `raw`, or create an `analytics` table. The Superset and database passwords, administrator password, and secret key live only in `.env`. `superset/exported_assets/asset_manifest.json` contains secret-free asset definitions and no connection URI or metadata export.

## Dashboards

| Dashboard | Purpose | Verified full-year values |
|---|---|---|
| [Energy Operations Overview](http://127.0.0.1:8090/superset/dashboard/1/) | Usage, daily trend, interval coverage, source load classes, and hour-of-day weekday/weekend pattern | 959,636.71 kWh; 35,040 intervals; 8,760 observed hours; 100% observed interval coverage |
| [Deviation & Incident Investigation](http://127.0.0.1:8090/superset/dashboard/2/) | Eligibility, reasons, hourly baseline detail, observed/expected trend, candidate detail, and sustained investigation register | 7,762 eligible (88.61%); 998 excluded; 1,263 consumption-positive hours; 1,343 distinct candidate hours; 238 sustained consumption incidents |
| [Power-Factor Review](http://127.0.0.1:8090/superset/dashboard/3/) | Descriptive PF trend, usage and reactive-energy context, review candidates and register | 105 PF-positive hours; 5 sustained PF incidents; 25 combined-priority hours |

Each dashboard defaults to the half-open facility-local range **2018-01-01 through 2019-01-01**. The time filter applies to the date-bearing charts and KPI cards; the full-year hour-of-day profile is deliberately outside it. The Overview load-type selector scopes only the source load-type chart. The PF Review load-type selector scopes only the descriptive PF-by-load chart. Both avoid filtering whole-hour totals by an interval class that may vary within the hour. The Investigation rule-type selector scopes only the rule-specific incident timeline and register. Candidate-hour KPIs remain distinct-hour counts. A June 2018 browser test changed the Overview to 65,404.64 kWh and 2,880 intervals; the load-type and rule-type selectors were also exercised in the browser.

## Data meaning

All energy totals use `SUM` of kWh or kVarh. Interval coverage is `100 × SUM(observed_interval_count) / SUM(expected_interval_count)` over the selected observed rows. Rule eligibility is `100 × eligible observed hours / all observed hours`; exclusion reasons partition the excluded hours. The 998 full-year exclusions are `insufficient_baseline_support`. The eligibility detail table shows one observed hour per row, including NULL expected kWh for excluded hours, current interval count, minimum comparable historical count, and exclusive reason. The observed/expected trend sums eligible hourly kWh by month for navigation; the detail table exposes the hourly values. Deviations and flags remain in the candidate-hour detail. This preserves the hourly rule grain.

The rule text displayed on the dashboards is: consumption **at least 10 kWh AND 30% above expected**; mean of four lagging PF readings **below 70%, with at least 20 kWh observed**; sustained **at least two consecutive qualifying hours for the same rule**. These are historical review heuristics, not confirmed plant operating limits, faults, or savings. One sustained incident row belongs to one rule; 243 rule-specific sustained incidents comprise 238 consumption and 5 PF incidents, and must not be added to the 1,343 distinct candidate hours. PF percentages are descriptive means, never additive billing measures. CO₂ is excluded from headline charts because its source unit is unresolved. Timestamps remain facility-local with unspecified timezone.

## Evidence and checks

Browser captures: [operations](../evidence/energy_operations_dashboard.png), [investigation](../evidence/deviation_investigation_dashboard.png), [power factor](../evidence/power_factor_review_dashboard.png), and [eligibility detail](../evidence/eligibility_detail.png). The machine-readable [Superset audit](../evidence/phase6_superset_audit.json) records all **28 successful nonempty chart queries**, 13 reconciled full-year KPI cards, June chart queries and KPI values, exact native select-filter scopes, read-only access checks, and unchanged 35,040 raw rows and 959,636.71 kWh. It also checks 7,762/998 eligibility, Phase 5 rule counts, 1,343 candidate hours, and 25 combined-priority hours.

For the complete regression run:

```powershell
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
```

If Superset is not ready, inspect `docker compose ps` and `docker compose logs --tail 100 superset superset-metadata`. Wait for both health checks before rerunning setup. If the database role has not been created, rerun `setup_analytics_role.py`. If views are missing, apply the Phase 3–5 SQL models as described in [START_HERE.md](../START_HERE.md). Do not use `docker compose down -v` for a restart; that removes named volumes.
