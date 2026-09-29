-- Grain: one row per observed hour. No breach or incident verdict is produced.
CREATE OR REPLACE VIEW analytics.energy_hourly_baseline_eligibility AS
WITH component_rollup AS (
    SELECT c.hour_start_local,
           count(*)::integer AS component_count,
           sum(c.current_interval_count)::integer AS component_interval_count,
           sum(c.current_component_usage_kwh) AS component_observed_usage_kwh,
           count(*) FILTER (WHERE NOT c.baseline_component_supported)::integer AS unsupported_component_count,
           sum(c.historical_sample_count)::integer AS historical_sample_count_total,
           min(c.historical_sample_count)::integer AS historical_sample_count_min,
           sum(c.expected_component_usage_kwh) AS supported_component_expected_sum_kwh,
           sum(c.component_p10_sum_kwh) AS supported_component_p10_sum_kwh,
           sum(c.component_p90_sum_kwh) AS supported_component_p90_sum_kwh,
           bool_and(c.week_status_value_count = 1 AND c.hour_of_day_value_count = 1) AS component_context_consistent,
           jsonb_object_agg(c.load_type, jsonb_build_object(
               'current_interval_count', c.current_interval_count,
               'current_usage_kwh', c.current_component_usage_kwh,
               'historical_sample_count', c.historical_sample_count,
               'historical_first_timestamp_local', c.historical_first_timestamp_local,
               'historical_last_timestamp_local', c.historical_last_timestamp_local,
               'median_15min_usage_kwh', c.median_15min_usage_kwh,
               'p10_15min_usage_kwh', c.p10_15min_usage_kwh,
               'p90_15min_usage_kwh', c.p90_15min_usage_kwh,
               'supported', c.baseline_component_supported
           )) AS load_type_component_evidence
    FROM analytics.energy_hourly_baseline_components AS c
    GROUP BY c.hour_start_local
), checks AS (
    SELECT h.hour_start_local,
           h.observed_interval_count AS current_observation_count,
           h.expected_interval_count AS expected_observation_count,
           h.coverage_pct AS current_coverage_pct,
           h.total_usage_kwh AS observed_usage_kwh,
           h.hour_start_local - INTERVAL '28 days' AS historical_window_start_local,
           h.hour_start_local AS historical_window_end_exclusive_local,
           r.component_count, r.component_interval_count,
           r.historical_sample_count_total, r.historical_sample_count_min,
           r.unsupported_component_count, r.load_type_component_evidence,
           r.supported_component_expected_sum_kwh,
           r.supported_component_p10_sum_kwh,
           r.supported_component_p90_sum_kwh,
           coalesce(h.observed_interval_count <> 4 OR h.coverage_pct <> 100, true) AS insufficient_current_coverage,
           (coalesce(r.unsupported_component_count, 0) > 0) AS insufficient_baseline_support,
           (h.total_usage_kwh IS NULL OR h.coverage_pct IS NULL
            OR coalesce(r.component_count, 0) = 0
            OR r.component_interval_count IS DISTINCT FROM h.observed_interval_count
            OR r.component_observed_usage_kwh IS DISTINCT FROM h.total_usage_kwh
            OR (r.unsupported_component_count = 0 AND r.supported_component_expected_sum_kwh IS NULL)
            OR r.component_context_consistent IS DISTINCT FROM true) AS other_data_problem
    FROM analytics.energy_hourly AS h
    LEFT JOIN component_rollup AS r ON r.hour_start_local = h.hour_start_local
)
SELECT c.hour_start_local, c.current_observation_count, c.expected_observation_count,
       c.current_coverage_pct, c.observed_usage_kwh,
       CASE WHEN NOT c.insufficient_current_coverage AND NOT c.insufficient_baseline_support
                      AND NOT c.other_data_problem
            THEN c.supported_component_expected_sum_kwh END AS expected_usage_kwh,
       CASE WHEN NOT c.insufficient_current_coverage AND NOT c.insufficient_baseline_support
                      AND NOT c.other_data_problem
            THEN c.supported_component_p10_sum_kwh END AS component_p10_sum_kwh,
       CASE WHEN NOT c.insufficient_current_coverage AND NOT c.insufficient_baseline_support
                      AND NOT c.other_data_problem
            THEN c.supported_component_p90_sum_kwh END AS component_p90_sum_kwh,
       c.historical_window_start_local, c.historical_window_end_exclusive_local,
       c.historical_sample_count_total, c.historical_sample_count_min,
       c.component_count, c.unsupported_component_count, c.load_type_component_evidence,
       (NOT c.insufficient_current_coverage AND NOT c.insufficient_baseline_support
        AND NOT c.other_data_problem) AS eligible,
       CASE WHEN c.other_data_problem THEN 'other_data_problem'
            WHEN c.insufficient_current_coverage AND c.insufficient_baseline_support
                THEN 'insufficient_current_and_baseline'
            WHEN c.insufficient_current_coverage THEN 'insufficient_current_coverage'
            WHEN c.insufficient_baseline_support THEN 'insufficient_baseline_support'
       END AS exclusion_reason,
       array_remove(ARRAY[
           CASE WHEN c.insufficient_current_coverage THEN 'insufficient_current_coverage' END,
           CASE WHEN c.insufficient_baseline_support THEN 'insufficient_baseline_support' END,
           CASE WHEN c.other_data_problem THEN 'other_data_problem' END
       ]::text[], NULL) AS secondary_reasons,
       'trailing_28d_load_hour_weekstatus_median_v1'::text AS baseline_method_version
FROM checks AS c;
