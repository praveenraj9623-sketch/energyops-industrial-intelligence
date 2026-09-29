# Historical SQL models (Phases 3–5)

All models are PostgreSQL views in `analytics`, sourced from `staging.stg_energy_readings`. Apply the scripts in dependency order with `python scripts/apply_phase3_models.py`. They can be applied repeatedly without adding business rows. The source/staging grain is one observation per recorded 15-minute, facility-local timestamp. No unobserved period is fabricated.

| View | Key and grain | Purpose |
|---|---|---|
| `analytics.energy_hourly` | `hour_start_local`; one observed local hour | Hourly energy and descriptive interval statistics. |
| `analytics.energy_daily` | `reading_date`; one observed local date | Daily energy and descriptive interval statistics. |
| `analytics.energy_hourly_by_load_type` | (`hour_start_local`, `load_type`); one observed hour and source load type | Reconciled breakdown of mixed-load hours. |
| `analytics.energy_daily_by_load_type` | (`reading_date`, `load_type`); one observed date and source load type | Reconciled breakdown of daily use. |
| `analytics.energy_hour_of_day_profile` | (`hour_of_day`, `week_status`); one hour-of-day and Weekday/Weekend pair | Historical time-of-day profile across observed hours. |
| `analytics.energy_load_type_summary` | `load_type`; one source load type | Historical load-type totals and share of all usage. |

## Equations, units and interpretation

- `total_usage_kwh = SUM(usage_kwh)` at the model grain. It is energy, **not** measured peak kW. `mean_15min_usage_kwh = AVG(usage_kwh)` and `max_15min_usage_kwh = MAX(usage_kwh)` describe source intervals; the maximum is not instantaneous demand.
- `total_lagging_reactive_power_kvarh` and `total_leading_reactive_power_kvarh` sum the corresponding source interval values in kVarh.
- Hourly `expected_interval_count = 4`; daily `expected_interval_count = 96`; `coverage_pct = observed_interval_count × 100 / expected_interval_count`. The fixed denominator applies to all-load periods only. Load-type breakdowns have no fixed expected count because multiple classes can occur within an hour or day.
- Hourly and daily models report simple mean, minimum and maximum source power-factor percentages. Breakdown and summary views report simple means. These are descriptive statistics, not a billing or electrical-system aggregate; percentages are never summed or assigned an invented weight.
- Hourly/daily counts for Light, Medium and Maximum Load are conditional interval counts. No dominant hour-level load type is assigned. The load-type breakdown views preserve mixed hours.
- The hour-of-day profile first sums each observed hour, then computes `mean_observed_hour_usage_kwh = AVG(hourly kWh)` for each hour-of-day and Weekday/Weekend pair. `mean_15min_usage_kwh = total kWh / observed interval count`. The load-type summary's `usage_share_pct = load-type kWh × 100 / all-load kWh`, with `NULLIF` protecting a zero denominator.
- `source_file_sha256` appears in all-load hourly/daily views only when every contributing interval has the same checksum; otherwise it is NULL. No CO₂ value appears in headline models because its unit is unresolved.

All times remain `TIMESTAMP WITHOUT TIME ZONE` facility-local labels. The source provides no timezone or DST rules, and these models neither convert to UTC nor infer such rules. The dataset has no machine ID, production/output, shift, tariff, fault or incident labels, so the models cannot establish waste, cost savings or equipment failures.

## Verified 2018 result

`python scripts/verify_phase3.py` independently aggregated the source CSV with `Decimal` and compared every hourly, daily and load-type group against PostgreSQL using absolute tolerance `0.000001` in source units. The verification also reapplied views twice and confirmed unchanged metrics, 35,040 raw rows and unchanged ingestion-run count. The machine-readable result and plan observations are in [`evidence/phase3_reconciliation.json`](../evidence/phase3_reconciliation.json).

| Measure | Source | Hourly | Daily | Each load-type breakdown |
|---|---:|---:|---:|---:|
| Observations represented | 35,040 | 35,040 | 35,040 | 35,040 |
| Usage (kWh) | 959,636.71 | 959,636.71 | 959,636.71 | 959,636.71 |
| Lagging reactive energy (kVarh) | 456,759.84 | 456,759.84 | 456,759.84 | 456,759.84 |
| Leading reactive energy (kVarh) | 135,638.04 | 135,638.04 | 135,638.04 | 135,638.04 |

The actual view counts are 8,760 hourly, 365 daily, 10,673 hourly-by-load-type, 971 daily-by-load-type, 48 hour-of-day profiles and 3 load-type summaries. There are no missing or partial hours/days in this source copy; all hourly and daily coverage values are 100%. Load-type interval counts are Light 18,072, Medium 9,696 and Maximum 7,272. Source Weekday/Weekend counts are 25,056/9,984. Some hours contain multiple load types; for example 2018-01-02 09:00 has 1 Light and 3 Medium intervals totaling 212.43 kWh.

Representative `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` queries over June 2018 took about 4 ms for an hourly date range, 4 ms for a daily date range and 2 ms for a date/load-type slice in the recorded run. The exact timings are in the evidence JSON. Hourly/daily plans used a sequential scan of the 35,040-row raw table followed by sort/aggregate; the load-type slice used the existing `readings_load_type_idx` bitmap scan. No additional index was justified by these plans. These timings describe this dataset and local machine only; they do not promise performance at larger scale.

Run `python scripts/verify_phase3.py` again after source or model changes. SQL scripts are `sql/10` through `sql/13`; no analytical tables or materialized views are created.

## Phase 4 views

Phase 4 adds `analytics.energy_hourly_baseline_components` (hour × current load type), `analytics.energy_hourly_baseline_eligibility` (one observed hour), and `analytics.energy_hourly_eligibility_status` (one exclusive status). It uses the Phase 3 hourly view and earlier raw/staging records. The exact 28-day trailing-window formula, 12-sample support gate, discrete percentiles, load-type composition calculation, exclusion reasons and limitations are in [BASELINE_AND_ELIGIBILITY.md](BASELINE_AND_ELIGIBILITY.md). These Phase 4 views contain expectations and rule eligibility only; Phase 5 applies separate candidate rules to eligible hours.

## Phase 5 views

Apply `python scripts/apply_phase5_models.py` after Phases 3–4. The four `sql/30`–`sql/33` definitions are nonmaterialized, rerunnable views. They preserve the original 8,760 observed-hour grain and Phase 4 eligibility. The exact thresholds, rationale, candidate semantics and limitations are in [INVESTIGATION_RULES.md](INVESTIGATION_RULES.md).

| View | Grain | Purpose |
|---|---|---|
| `analytics.energy_rule_evaluation` | One observed local hour | Eligibility, exclusions, source context, NULL-safe excess/deviation, descriptive mean lagging PF, independent booleans, combined priority and rule version/thresholds. |
| `analytics.energy_candidate_hours` | One eligible hour with either positive rule | Hourly conditions; a singleton is retained here. |
| `analytics.energy_candidate_incidents` | One sustained rule-specific island | Deterministic key, first/last candidate hour, observed-hour duration, peaks, load-type evidence and review status. |
| `analytics.energy_rule_summary` | One row per fixed rule type | Evaluated, eligible, excluded, positive and sustained counts; fixed rule rows appear even if zero. |

The incident view uses `LAG`, `CASE` and cumulative `SUM() OVER` on separate rule streams, then retains islands of at least two exactly adjacent hours. The last candidate hour is an observed timestamp, not a proved event end. `python scripts/verify_phase5.py` writes source-backed decisions, independent Python island counts, rerun reconciliation and query plans to [phase5_rule_audit.json](../evidence/phase5_rule_audit.json).
