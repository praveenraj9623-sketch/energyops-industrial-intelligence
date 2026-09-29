-- Load-type coverage has no fixed denominator: an hour/day may contain several load types.
CREATE OR REPLACE VIEW analytics.energy_hourly_by_load_type AS
SELECT
    s.hour_start_local,
    s.load_type,
    count(*)::integer AS observed_interval_count,
    sum(s.usage_kwh) AS total_usage_kwh,
    avg(s.usage_kwh) AS mean_15min_usage_kwh,
    max(s.usage_kwh) AS max_15min_usage_kwh,
    sum(s.lagging_reactive_power_kvarh) AS total_lagging_reactive_power_kvarh,
    sum(s.leading_reactive_power_kvarh) AS total_leading_reactive_power_kvarh,
    avg(s.lagging_power_factor_pct) AS mean_lagging_power_factor_pct,
    avg(s.leading_power_factor_pct) AS mean_leading_power_factor_pct
FROM staging.stg_energy_readings AS s
GROUP BY s.hour_start_local, s.load_type;

CREATE OR REPLACE VIEW analytics.energy_daily_by_load_type AS
SELECT
    s.reading_date,
    s.load_type,
    count(*)::integer AS observed_interval_count,
    sum(s.usage_kwh) AS total_usage_kwh,
    avg(s.usage_kwh) AS mean_15min_usage_kwh,
    max(s.usage_kwh) AS max_15min_usage_kwh,
    sum(s.lagging_reactive_power_kvarh) AS total_lagging_reactive_power_kvarh,
    sum(s.leading_reactive_power_kvarh) AS total_leading_reactive_power_kvarh,
    avg(s.lagging_power_factor_pct) AS mean_lagging_power_factor_pct,
    avg(s.leading_power_factor_pct) AS mean_leading_power_factor_pct
FROM staging.stg_energy_readings AS s
GROUP BY s.reading_date, s.load_type;
