# Phase 4 historical baseline and eligibility

Phase 4 prepares a historical expectation and an explicit eligibility decision for **observed** facility-local hours. It does not flag breaches, set alert thresholds, infer waste, or create incidents. The source has one facility-level series; an hour can contain several load types.

## Fixed method (version `trailing_28d_load_hour_weekstatus_median_v1`)

The parameters were chosen before inspecting any candidate-alert outcomes: a trailing **28 calendar-day** window and at least **12 prior 15-minute readings for each load type present in the evaluated hour**. This gives several comparable days while limiting seasonal drift; 12 is a minimum-support gate, not a statistical guarantee. There was no alert-count tuning in this phase.

For an hour starting at local wall time `H`, the historical window is **[`H − 28 days`, `H`)**. The end is exclusive. A prior reading is comparable only when it shares the current component's source `Load_Type`, hour of day, and `WeekStatus` (`Weekday` or `Weekend`). The comparison does not require the same minute within the hour. All historical timestamps are strictly earlier than `H`, which is stricter than being earlier than each of the hour's current readings. Facility-local timestamps are kept as `TIMESTAMP WITHOUT TIME ZONE`; the source timezone remains unspecified. No UTC or DST conversion is attempted.

For each `(H, load_type)` component, the view reports the current interval count, observed component kWh, historical sample count, first/last historical timestamps, and **discrete** p10, median and p90 of historical 15-minute kWh. `percentile_disc` returns an observed value; for even sample sizes the median is the lower middle observation. A component is supported when its contextual labels are consistent, its historical count is at least 12, and the distribution values are non-NULL.

For a fully eligible hour, `expected_usage_kwh = Σ(current_interval_count_for_type × historical_median_15min_kwh_for_type)`. This uses the **actual current-hour load-type composition**; no dominant type is assigned. The same weighted sum of component p10/p90 values is exposed as `component_p10_sum_kwh` and `component_p90_sum_kwh`. Those sums are **not** quantiles of the hourly-total distribution and are not Phase 5 thresholds. CO₂ is excluded because its unit is unresolved.

## Eligibility and exclusions

An observed hour is eligible only when it has exactly 4 valid current intervals (100% coverage), every present load-type component has adequate comparable history, and required values and cross-component reconciliation are non-NULL and consistent. A partially supported hour has `expected_usage_kwh = NULL`; it is never evaluated silently. The final view reports the 28-day window, total and minimum component historical counts, component JSON evidence, `eligible`, an exclusive `exclusion_reason`, secondary reasons, and method version.

Exclusive reasons are `insufficient_current_coverage`, `insufficient_baseline_support`, `insufficient_current_and_baseline`, and `other_data_problem`. When an hour has multiple failures, `secondary_reasons` retains each underlying condition; the exclusive reason is one value. Other data problems take precedence over the coverage/support categories. Excluded hours are **not** equipment downtime.

Views and grains:

| View | Grain |
|---|---|
| `analytics.energy_hourly_baseline_components` | One observed hour × load type present in that hour. |
| `analytics.energy_hourly_baseline_eligibility` | One observed facility-local hour. |
| `analytics.energy_hourly_eligibility_status` | One observed exclusive status category. |

`python scripts/apply_phase4_models.py` applies rerunnable SQL files `sql/19` through `sql/22`. File `19_baseline_index.sql` adds one measured-need index on load type, week status, hour of day and timestamp, including `usage_kwh`; it does not change raw records. The new views depend on Phase 3's hourly view and the Phase 2 raw/staging layer. All remain ordinary views.

## Verified result and performance

For the preserved 2018 source, **7,762 of 8,760 observed hours are eligible (88.6073%)**. The other **998 (11.3927%)** are exclusively `insufficient_baseline_support`. There are zero `insufficient_current_coverage`, zero combined coverage/support exclusions and zero `other_data_problem` exclusions. Eligible + excluded = 8,760, and exclusive reason counts sum to 998. The early-year warm-up and changes in load-type context explain why a complete hourly grid can still lack comparable history. These counts are eligibility only; they say nothing about future breaches.

[`evidence/phase4_baseline_audit.json`](../evidence/phase4_baseline_audit.json) records independent CSV checks of nine selected hours: the first observed hour, early unsupported, later eligible, mixed-load, weekday/weekend, and year-end examples. It checks exact window bounds, every selected comparable timestamp's strict precedence and inclusion in the window, component sample counts, discrete percentiles, expected kWh, exclusive reasons, and agreement with PostgreSQL. A database-wide component check found **zero** historical timestamps outside their windows or reaching the evaluated hour. The audit reapplies the models twice and confirms unchanged status metrics, 35,040 raw readings, 959,636.71 raw kWh, and ingestion-run count.

The first measured full status-view plan took about **3.0 seconds** and hit roughly **1.49 million** shared buffer pages through 10,673 repeated timestamp-index scans. After adding the contextual baseline index, the latest full status query took about **0.18 seconds** with **37,734** shared hits; its historical lookup used an index-only scan. A representative one-week eligibility query took about **0.17 seconds**. Exact timings vary by run; the evidence JSON stores the current measured plans. The index is justified by this specific measured bottleneck, not by assumed performance at larger scale.

## Limits and reproduction

The 28-day, 12-sample design is an explicit engineering choice, not a learned causal model. Source load types have no documented classification method, and weekday/weekend plus hour of day do not capture product mix, production volume, shift schedule, holidays, maintenance, tariffs or weather. Historical medians describe comparable recorded intervals; deviations from them will require separate eligibility, threshold and investigation design in later phases. No equipment or financial conclusion follows from baseline eligibility.

From the repository root with the existing PostgreSQL volume healthy:

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
