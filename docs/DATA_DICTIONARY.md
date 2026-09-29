# Data dictionary

The full source-to-canonical mapping, type, unit, validation and interpretation for every column is in [DATA_CONTRACT.md](DATA_CONTRACT.md). Phase 2 implements these canonical fields in `raw.steel_energy_readings` and `staging.stg_energy_readings`; `date` maps to `source_timestamp_local`.

The source has no plant or machine ID, production volume, output quantity, price or tariff, incident label, shift schedule, or emissions methodology. `Load_Type` is a source-provided category, not an equipment state. `NSM` duplicates the time-of-day component of `date` and provides a consistency check.
