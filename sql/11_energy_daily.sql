-- Grain: one row per observed facility-local date.
CREATE OR REPLACE VIEW analytics.energy_daily AS
SELECT
    s.reading_date,
    count(*)::integer AS observed_interval_count,
    96::integer AS expected_interval_count,
    (count(*)::numeric * 100 / NULLIF(96, 0)) AS coverage_pct,
    sum(s.usage_kwh) AS total_usage_kwh,
    avg(s.usage_kwh) AS mean_15min_usage_kwh,
    max(s.usage_kwh) AS max_15min_usage_kwh,
    sum(s.lagging_reactive_power_kvarh) AS total_lagging_reactive_power_kvarh,
    sum(s.leading_reactive_power_kvarh) AS total_leading_reactive_power_kvarh,
    avg(s.lagging_power_factor_pct) AS mean_lagging_power_factor_pct,
    min(s.lagging_power_factor_pct) AS min_lagging_power_factor_pct,
    max(s.lagging_power_factor_pct) AS max_lagging_power_factor_pct,
    avg(s.leading_power_factor_pct) AS mean_leading_power_factor_pct,
    min(s.leading_power_factor_pct) AS min_leading_power_factor_pct,
    max(s.leading_power_factor_pct) AS max_leading_power_factor_pct,
    count(*) FILTER (WHERE s.load_type = 'Light_Load')::integer AS light_load_interval_count,
    count(*) FILTER (WHERE s.load_type = 'Medium_Load')::integer AS medium_load_interval_count,
    count(*) FILTER (WHERE s.load_type = 'Maximum_Load')::integer AS maximum_load_interval_count,
    CASE WHEN count(DISTINCT s.source_file_sha256) = 1 THEN min(s.source_file_sha256) END AS source_file_sha256
FROM staging.stg_energy_readings AS s
GROUP BY s.reading_date;
