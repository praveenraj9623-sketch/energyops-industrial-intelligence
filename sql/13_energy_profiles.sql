-- Grain: hour-of-day (0–23) x source weekday/weekend classification.
CREATE OR REPLACE VIEW analytics.energy_hour_of_day_profile AS
WITH observed_hours AS (
    SELECT s.hour_start_local, s.hour_of_day, s.week_status,
           count(*)::integer AS observed_interval_count,
           sum(s.usage_kwh) AS total_usage_kwh
    FROM staging.stg_energy_readings AS s
    GROUP BY s.hour_start_local, s.hour_of_day, s.week_status
)
SELECT
    hour_of_day,
    week_status,
    count(*)::integer AS observed_hour_count,
    sum(observed_interval_count)::integer AS observed_interval_count,
    sum(total_usage_kwh) AS total_usage_kwh,
    avg(total_usage_kwh) AS mean_observed_hour_usage_kwh,
    sum(total_usage_kwh) / NULLIF(sum(observed_interval_count), 0) AS mean_15min_usage_kwh
FROM observed_hours
GROUP BY hour_of_day, week_status;

-- Grain: one row per source load type across all observed intervals.
CREATE OR REPLACE VIEW analytics.energy_load_type_summary AS
WITH by_type AS (
    SELECT s.load_type,
           count(*)::integer AS observed_interval_count,
           sum(s.usage_kwh) AS total_usage_kwh,
           avg(s.usage_kwh) AS mean_15min_usage_kwh,
           sum(s.lagging_reactive_power_kvarh) AS total_lagging_reactive_power_kvarh,
           sum(s.leading_reactive_power_kvarh) AS total_leading_reactive_power_kvarh,
           avg(s.lagging_power_factor_pct) AS mean_lagging_power_factor_pct,
           avg(s.leading_power_factor_pct) AS mean_leading_power_factor_pct
    FROM staging.stg_energy_readings AS s
    GROUP BY s.load_type
), all_types AS (
    SELECT sum(total_usage_kwh) AS total_usage_kwh FROM by_type
)
SELECT b.load_type, b.observed_interval_count, b.total_usage_kwh,
       b.total_usage_kwh * 100 / NULLIF(a.total_usage_kwh, 0) AS usage_share_pct,
       b.mean_15min_usage_kwh,
       b.total_lagging_reactive_power_kvarh,
       b.total_leading_reactive_power_kvarh,
       b.mean_lagging_power_factor_pct,
       b.mean_leading_power_factor_pct
FROM by_type AS b CROSS JOIN all_types AS a;
