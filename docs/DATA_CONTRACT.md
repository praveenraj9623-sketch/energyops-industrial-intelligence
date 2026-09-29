# Source data contract (Phase 1)

**Grain:** one historical steel-industry energy observation per recorded timestamp, expected at 15-minute intervals. The source timestamp is a local wall-clock label; no timezone or UTC offset is provided. All 11 source columns are required, ordered as below, and non-null in the supplied CSV. Canonical names are planned for later ingestion; Phase 1 retains the original CSV unchanged. Numeric measures accept finite values only.

| Exact source name | Canonical destination | Type | Unit | Nullable | Accepted values and validation | Meaning and limitation |
|---|---|---|---|---|---|---|
| `date` | `source_timestamp` | timestamp, `%d/%m/%Y %H:%M` | local time, zone unspecified | No | Parseable; unique; 15-minute grid; calendar date within source coverage | Observation time. Do not assume UTC or a specific Korean timezone until confirmed. |
| `Usage_kWh` | `usage_kwh` | decimal | kWh | No | Finite, >= 0 | Recorded interval electricity consumption; no production denominator or tariff. |
| `Lagging_Current_Reactive.Power_kVarh` | `lagging_reactive_power_kvarh` | decimal | kVarh | No | Finite, >= 0 | Lagging reactive energy; measurement method unspecified. |
| `Leading_Current_Reactive_Power_kVarh` | `leading_reactive_power_kvarh` | decimal | kVarh | No | Finite, >= 0 | Leading reactive energy; measurement method unspecified. |
| `CO2(tCO2)` | `co2_value` | decimal | **unverified**; UCI table states ppm, label implies tCO2 | No | Finite, >= 0 | Source CO₂-associated value. No emissions totals or carbon claims until unit and derivation are verified. |
| `Lagging_Current_Power_Factor` | `lagging_power_factor_pct` | decimal | % | No | Finite, 0–100 inclusive | Lagging power factor as reported; source does not establish incident thresholds. |
| `Leading_Current_Power_Factor` | `leading_power_factor_pct` | decimal | % | No | Finite, 0–100 inclusive | Leading power factor as reported; source does not establish incident thresholds. |
| `NSM` | `seconds_from_midnight` | integer | seconds | No | 0–86399; equals timestamp time of day | Number of seconds since midnight; redundant with `date`. |
| `WeekStatus` | `week_status` | string | none | No | `Weekday`, `Weekend`; agrees with date | Calendar grouping, not shift schedule. |
| `Day_of_week` | `day_of_week` | string | none | No | Monday through Sunday; agrees with date | Calendar day label. |
| `Load_Type` | `load_type` | string | none | No | `Light_Load`, `Medium_Load`, `Maximum_Load` | Source load class; classification method and operational meaning are not documented. |

The source uses `Weekday`/`Weekend` strings, despite the UCI description mentioning 0/1. The UCI page says “9 features” but its variables table and the CSV contain 11 columns; the downloaded CSV controls this implementation. See [source attribution](SOURCE_ATTRIBUTION.md) and [quality audit](DATA_QUALITY.md).

Future ingestion must preserve original values and source identity, reject or quarantine contract violations with a reason, and reconcile accepted + quarantined counts to the source row count. No conversion of `co2_value` is authorized by this contract.
