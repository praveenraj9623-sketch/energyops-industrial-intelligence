-- EXPLAIN ANALYZE before this index: ~3.0 s and ~1.5 million shared buffer hits
-- for the eligibility-status view. This index serves its actual historical lookup.
CREATE INDEX IF NOT EXISTS readings_baseline_context_time_idx
ON raw.steel_energy_readings (
    load_type,
    week_status,
    (EXTRACT(HOUR FROM source_timestamp_local)::integer),
    source_timestamp_local
) INCLUDE (usage_kwh);
