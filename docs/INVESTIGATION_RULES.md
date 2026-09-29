# Phase 5 historical candidate investigation rules

**Initial rule record — fixed before querying final candidate counts.** Version: `phase5_candidate_rules_v1`. This phase classifies historical hours for engineering review. A candidate is not confirmed waste, a plant fault, a billing event, or an equipment incident. The 2018 source has no incident labels, production output, tariff, or machine identifiers. No thresholds were adjusted to target a candidate count; any future change requires a new version and a documented reason.

## Source profiling used to choose the rules

The 35,040 lagging power-factor readings range from 0 to 100%, with p10 49.99%, median 87.96%, and p90 100%. By source load type, the lagging power-factor median is 66.27% for Light Load, 96.82% for Medium Load, and 91.71% for Maximum Load. Mean 15-minute usage is 8.63, 38.45 and 59.27 kWh for those classes, respectively. Hourly usage has p25 12.99 kWh, median 18.97 kWh and p75 203.84 kWh. The hourly mean lagging-power-factor median is 87.96%; hours with mean at or below 70% often have low usage. These are descriptive source values, not operating limits or causal evidence.

## Hourly conditions

Both conditions require `analytics.energy_hourly_baseline_eligibility.eligible = true`, exactly four observed 15-minute readings, and non-NULL inputs. All timestamps remain facility-local with unspecified timezone. A missing or ineligible hour cannot be flagged.

**Consumption deviation candidate:** Let `excess_kwh = observed_usage_kwh − expected_usage_kwh` and `deviation_pct = 100 × excess_kwh / NULLIF(expected_usage_kwh, 0)`. Flag when **excess_kwh ≥ 10 kWh AND deviation_pct ≥ 30%**. The 30% condition asks for a material relative departure from the context-specific Phase 4 median-sum expectation. The 10 kWh floor, close to a low-load hour's typical total, prevents tiny absolute changes on low baselines from qualifying. Equality qualifies. A zero expected value yields NULL deviation and no flag. The Phase 4 sum of component p90 values may be shown as context; it is not a calibrated hourly p90 and is **not** a rule threshold.

**Lagging power-factor review candidate:** Use the arithmetic **mean of the four 15-minute lagging power-factor percentages** (`analytics.energy_hourly.mean_lagging_power_factor_pct`). Flag when this mean is **strictly below 70%** and hourly observed energy is **at least 20 kWh**. The low 70% review line is deliberately more selective than a billing-style target; it identifies a pronounced low descriptive mean. The 20 kWh gate, near the overall hourly median of 18.97 kWh, reduces low-load/near-idle review noise shown by the source profile. It is not a plant operating standard. A reading below 70% alone, or an hourly mean below 70% during light usage, does not qualify. No power-factor percentages are summed or treated as a billing-grade aggregate.

`combined_priority` is true when **both** conditions are true in the same eligible hour. It is a review-priority label, not a third rule type or a third incident stream. The hourly candidate view retains each condition separately. CO₂ is outside both rules because its source unit remains unresolved.

## Persistence and grouping

Each rule type is grouped independently. Candidate hours are consecutive only when their facility-local starts differ by exactly one hour and **both** meet that same rule. An ineligible, absent, or non-positive hour breaks a group. `LAG()` identifies the preceding candidate hour, `CASE` marks a new island, and cumulative `SUM() OVER` assigns an island number. A sustained candidate incident needs **at least two consecutive positive hours**. A single positive hour remains an hourly candidate, not an incident. Combined-priority hours have no separate island grouping.

Incident keys are deterministic MD5 hashes of the rule version, rule type and first candidate hour. An incident records first and last observed candidate hours, the inclusive count of qualifying hourly periods, peak observed hourly kWh, peak **positive** excess kWh, highest signed deviation percentage, minimum hourly mean lagging power factor, and per-hour load-type composition. `duration_observed_hours` is the count of observed candidate hours; `last_candidate_hour_local` is **not** a verified incident end time. Status is always `candidate for review`.

## Views and verification

| View | Grain |
|---|---|
| `analytics.energy_rule_evaluation` | One row per observed hour, including eligibility, exclusion and both flags. |
| `analytics.energy_candidate_hours` | One eligible hour where either condition is positive. |
| `analytics.energy_candidate_incidents` | One sustained island per rule type and deterministic start key. |
| `analytics.energy_rule_summary` | One row per fixed rule type, including zero-result categories. |

SQL files `sql/30` through `sql/33` are rerunnable with `python scripts/apply_phase5_models.py`. `python scripts/verify_phase5.py` writes `evidence/phase5_rule_audit.json` after independently reproducing selected decisions from the source CSV and verified Phase 4 baseline. Phase 4's 28-day/12-sample method and eligibility are preserved. No scheduled or live alert delivery is implemented.

## Verified historical result

No thresholds were changed after inspecting candidate outcomes. The 8,760 observed hours comprise 7,762 eligible and 998 excluded hours; the excluded hours remain Phase 4 `insufficient_baseline_support` cases. No excluded hour has a positive flag. The two rules overlap in 25 hours, so their positive-hour counts cannot be added to obtain distinct candidate hours.

| Measure | Consumption deviation | Lagging power-factor review |
|---|---:|---:|
| Eligible hours evaluated | 7,762 | 7,762 |
| Condition-positive hours, including singletons | 1,263 | 105 |
| Sustained candidate incidents (at least two hours) | 238 | 5 |
| Positive hours inside sustained incidents | 986 | 12 |

There are **1,343 distinct candidate hours** and **25 combined-priority hours**. For example, the consumption candidate incident from **2018-01-05 18:00 through 19:00** has two observed candidate hours, peak hourly energy 246.78 kWh and peak positive excess 85.78 kWh. A power-factor review candidate incident from **2018-02-08 02:00 through 04:00** has three observed candidate hours. The timestamps are local labels and these periods are not confirmed plant events.

The Python audit reads all 35,040 original CSV rows, independently computes hourly usage and the arithmetic mean lagging power factor, reproduces all hourly rule decisions, reconstructs each rule's consecutive-hour islands and compares them with SQL. Its 19 source-backed baseline samples include warm-up, eligible non-positive, mixed-load, weekday/weekend, year-end, condition-positive, first/last incident, across-midnight and gap-boundary hours. For each sample, Python recalculates Phase 4 history from the CSV and verifies the 28-day boundaries, comparable sample counts, median-based expectation and strict earlier-than-hour comparisons. The audit reapplies Phase 5 twice and confirms unchanged raw count **35,040**, usage **959,636.71 kWh**, ingestion history, summary and stable incident keys.

Representative PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` on the local 2018 dataset took roughly **0.2 s** for a June evaluation week, **0.6 s** for the full incident view and **1.4 s** for the full summary in recorded runs. The plans use the existing `readings_baseline_context_time_idx` for Phase 4 historical comparisons. The full summary recomputes nonmaterialized baseline and candidate views, so it costs more than a narrow evaluation; no new index was justified on 35,040 raw rows. Timings vary by machine and cache state. Exact plan nodes and timings are in [phase5_rule_audit.json](../evidence/phase5_rule_audit.json).

To reproduce after the Phase 1–4 setup in [START_HERE.md](../START_HERE.md):

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

The rules are descriptive historical review heuristics; no incident labels exist to estimate precision or false-positive rates. Mean power factor is not a billing-grade aggregate, the 20 kWh usage gate and 70% line are not plant-specific electrical standards, and the consumption comparison omits production output, tariff, equipment and shift context. Candidate incident duration counts observed positive hourly periods only. A source with missing hours could conceal activity between observations. Dashboarding, live monitoring and scheduled alert delivery remain future phases.
