-- Fixed before eligibility inspection: 28 trailing calendar days, minimum 12 comparable intervals.
-- Grain: observed facility-local hour x load type present in that hour.
-- The historical interval [hour_start_local - 28 days, hour_start_local) excludes the current hour.
CREATE OR REPLACE VIEW analytics.energy_hourly_baseline_components AS
WITH current_components AS (
    SELECT s.hour_start_local, s.load_type,
           min(s.week_status) AS week_status,
           min(s.hour_of_day)::integer AS hour_of_day,
           count(DISTINCT s.week_status)::integer AS week_status_value_count,
           count(DISTINCT s.hour_of_day)::integer AS hour_of_day_value_count,
           count(*)::integer AS current_interval_count,
           sum(s.usage_kwh) AS current_component_usage_kwh
    FROM staging.stg_energy_readings AS s
    GROUP BY s.hour_start_local, s.load_type
), samples AS (
    SELECT c.*,
           c.hour_start_local - INTERVAL '28 days' AS historical_window_start_local,
           c.hour_start_local AS historical_window_end_exclusive_local,
           h.historical_sample_count,
           h.historical_first_timestamp_local,
           h.historical_last_timestamp_local,
           h.p10_15min_usage_kwh,
           h.median_15min_usage_kwh,
           h.p90_15min_usage_kwh
    FROM current_components AS c
    LEFT JOIN LATERAL (
        SELECT count(*)::integer AS historical_sample_count,
               min(p.source_timestamp_local) AS historical_first_timestamp_local,
               max(p.source_timestamp_local) AS historical_last_timestamp_local,
               percentile_disc(0.10) WITHIN GROUP (ORDER BY p.usage_kwh) AS p10_15min_usage_kwh,
               percentile_disc(0.50) WITHIN GROUP (ORDER BY p.usage_kwh) AS median_15min_usage_kwh,
               percentile_disc(0.90) WITHIN GROUP (ORDER BY p.usage_kwh) AS p90_15min_usage_kwh
        FROM raw.steel_energy_readings AS p
        WHERE p.source_timestamp_local >= c.hour_start_local - INTERVAL '28 days'
          AND p.source_timestamp_local < c.hour_start_local
          AND EXTRACT(HOUR FROM p.source_timestamp_local)::integer = c.hour_of_day
          AND p.week_status = c.week_status
          AND p.load_type = c.load_type
    ) AS h ON true
)
SELECT s.*,
       (s.week_status_value_count = 1 AND s.hour_of_day_value_count = 1
        AND s.historical_sample_count >= 12
        AND s.median_15min_usage_kwh IS NOT NULL
        AND s.p10_15min_usage_kwh IS NOT NULL
        AND s.p90_15min_usage_kwh IS NOT NULL) AS baseline_component_supported,
       CASE WHEN s.week_status_value_count = 1 AND s.hour_of_day_value_count = 1
                  AND s.historical_sample_count >= 12 AND s.median_15min_usage_kwh IS NOT NULL
            THEN s.current_interval_count * s.median_15min_usage_kwh END AS expected_component_usage_kwh,
       CASE WHEN s.week_status_value_count = 1 AND s.hour_of_day_value_count = 1
                  AND s.historical_sample_count >= 12 AND s.p10_15min_usage_kwh IS NOT NULL
            THEN s.current_interval_count * s.p10_15min_usage_kwh END AS component_p10_sum_kwh,
       CASE WHEN s.week_status_value_count = 1 AND s.hour_of_day_value_count = 1
                  AND s.historical_sample_count >= 12 AND s.p90_15min_usage_kwh IS NOT NULL
            THEN s.current_interval_count * s.p90_15min_usage_kwh END AS component_p90_sum_kwh
FROM samples AS s;
