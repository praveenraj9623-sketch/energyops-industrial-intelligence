-- Read-only counts for manual inspection; verify_phase2.py performs the full reconciliation.
SELECT 'raw' AS layer, count(*) AS rows FROM raw.steel_energy_readings
UNION ALL SELECT 'staging', count(*) FROM staging.stg_energy_readings
UNION ALL SELECT 'rejections', count(*) FROM raw.steel_energy_rejections;
