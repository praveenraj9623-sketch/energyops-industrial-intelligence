# Source data-quality audit — Phase 1

**Assessment:** The downloaded CSV is usable for historical, interval-level energy analysis subject to the semantic limitations below. The profile is reproducible with `python scripts/profile_source.py`; full machine-readable evidence is in [`evidence/source_profile.json`](../evidence/source_profile.json). No source rows were deleted or changed.

| Check | Computed result | Disposition and risk |
|---|---:|---|
| Shape | 35,040 rows × 11 columns | Matches 365 days × 96 intervals. Accepted. |
| Timestamp | 2018-01-01 00:00 through 2018-12-31 23:45; 35,040 parsed, 0 failed | Accepted. Timezone remains unverified. |
| Completeness | 0 missing values in every column | Accepted. |
| Duplicates | 0 complete duplicate rows; 0 duplicate timestamps; 0 duplicate timestamp groups | Accepted for intended grain. |
| Intervals | 35,040 expected, 35,040 unique observed; 0 gaps; 0 off-grid timestamps | Accepted. |
| Categories | 0 unexpected WeekStatus, Day_of_week or Load_Type values | Accepted. Week/day labels match parsed dates: 0 mismatches. |
| Numeric | 0 nonnumeric, infinite or negative values in all seven numeric columns | Accepted. |
| Power factors | 0 outside 0–100 in either field | Accepted. |
| NSM | 0–85,500 seconds; 0 out of range, noninteger or inconsistent with timestamp | Accepted. |

Observed finite numeric ranges: usage 0–157.18 kWh; lagging reactive energy 0–96.91 kVarh; leading reactive energy 0–27.76 kVarh; `CO2(tCO2)` 0–0.07 (unit unverified); lagging power factor 0–100%; leading power factor 0–100%.

Category distribution: Light_Load 18,072; Medium_Load 9,696; Maximum_Load 7,272. Weekday 25,056; Weekend 9,984. Day-of-week: Monday 5,088; Tuesday through Sunday 4,992 each. These sums reconcile to 35,040.

## Risks and Phase 2 requirements

- **Requiring clarification:** UCI labels the CO₂ column `CO2(tCO2)` but states its unit as `ppm`. Do not convert, total, or interpret it as tonnes until source methodology is confirmed.
- **Requiring clarification:** Timestamp timezone is absent. Preserve wall-clock values and do not assert UTC instants.
- **Accepted with limitation:** UCI summary says 9 features, while its variables table and actual CSV show 11 columns. The CSV schema is authoritative for this contract. The UCI WeekStatus description says 0/1, while actual values are `Weekday`/`Weekend`.
- **Accepted with limitation:** There are no production or incident labels; a deviation is only an investigation candidate.
- **Quarantined in a future phase:** None in this source copy. Future invalid rows must retain their original payload, source row reference and rejection reason; no silent correction or deletion.

The Phase 2 loader reconciles source count = accepted count + quarantined count, compares the checksum with this intake, applies timestamp uniqueness and numeric/category checks, and requires review of new exceptions before publishing analytical results. The current clean profile is not evidence that future files will be clean.

Phase 2 implements the typed raw constraints, row quarantine and reconciliation described in [INGESTION.md](INGESTION.md). The database result is recorded separately in `evidence/phase2_reconciliation.json` when the verification command runs; this Phase 1 audit remains the independent source baseline.
