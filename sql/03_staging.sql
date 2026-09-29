CREATE OR REPLACE VIEW staging.stg_energy_readings AS
SELECT
    r.source_timestamp_local,
    r.source_timestamp_local::date AS reading_date,
    date_trunc('hour', r.source_timestamp_local) AS hour_start_local,
    EXTRACT(YEAR FROM r.source_timestamp_local)::integer AS year,
    EXTRACT(MONTH FROM r.source_timestamp_local)::integer AS month,
    EXTRACT(DAY FROM r.source_timestamp_local)::integer AS day_of_month,
    EXTRACT(HOUR FROM r.source_timestamp_local)::integer AS hour_of_day,
    EXTRACT(MINUTE FROM r.source_timestamp_local)::integer AS minute_of_hour,
    EXTRACT(ISODOW FROM r.source_timestamp_local)::integer AS iso_day_of_week,
    trim(to_char(r.source_timestamp_local, 'Day')) AS day_name,
    r.day_of_week AS source_day_of_week,
    r.week_status,
    r.load_type,
    r.usage_kwh,
    r.lagging_reactive_power_kvarh,
    r.leading_reactive_power_kvarh,
    r.co2_value,
    r.lagging_power_factor_pct,
    r.leading_power_factor_pct,
    r.seconds_from_midnight,
    r.ingestion_run_id,
    r.source_file_sha256,
    (r.day_of_week = trim(to_char(r.source_timestamp_local, 'Day'))) AS day_name_matches,
    (r.week_status = CASE WHEN EXTRACT(ISODOW FROM r.source_timestamp_local) IN (6,7)
                          THEN 'Weekend' ELSE 'Weekday' END) AS week_status_matches,
    (r.seconds_from_midnight = EXTRACT(HOUR FROM r.source_timestamp_local)::integer * 3600
                               + EXTRACT(MINUTE FROM r.source_timestamp_local)::integer * 60) AS seconds_from_midnight_matches
FROM raw.steel_energy_readings AS r;
