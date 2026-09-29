-- One row per observed facility-local hour. Thresholds fixed in INVESTIGATION_RULES.md.
CREATE OR REPLACE VIEW analytics.energy_rule_evaluation AS
WITH measures AS (
    SELECT e.*, h.mean_lagging_power_factor_pct,
           h.observed_interval_count AS rule_observed_interval_count,
           e.observed_usage_kwh - e.expected_usage_kwh AS excess_kwh,
           100 * (e.observed_usage_kwh - e.expected_usage_kwh)
               / NULLIF(e.expected_usage_kwh, 0) AS deviation_pct
    FROM analytics.energy_hourly_baseline_eligibility AS e
    JOIN analytics.energy_hourly AS h USING (hour_start_local)
)
SELECT m.hour_start_local, m.eligible, m.exclusion_reason, m.secondary_reasons,
       m.current_observation_count, m.expected_observation_count,
       m.current_coverage_pct, m.observed_usage_kwh, m.expected_usage_kwh,
       m.excess_kwh, m.deviation_pct, m.component_p90_sum_kwh,
       m.mean_lagging_power_factor_pct, m.rule_observed_interval_count,
       m.historical_window_start_local, m.historical_window_end_exclusive_local,
       m.historical_sample_count_total, m.historical_sample_count_min,
       m.load_type_component_evidence, m.baseline_method_version,
       coalesce((m.eligible IS TRUE AND m.current_observation_count = 4
        AND m.rule_observed_interval_count = 4 AND m.excess_kwh >= 10
        AND m.deviation_pct >= 30), false) AS consumption_deviation_candidate,
       coalesce((m.eligible IS TRUE AND m.current_observation_count = 4
        AND m.rule_observed_interval_count = 4
        AND m.mean_lagging_power_factor_pct < 70
        AND m.observed_usage_kwh >= 20), false) AS lagging_power_factor_review_candidate,
       coalesce(((m.eligible IS TRUE AND m.current_observation_count = 4
         AND m.rule_observed_interval_count = 4 AND m.excess_kwh >= 10
         AND m.deviation_pct >= 30)
        AND (m.mean_lagging_power_factor_pct < 70
             AND m.observed_usage_kwh >= 20)), false) AS combined_priority,
       10::numeric AS minimum_excess_kwh, 30::numeric AS minimum_deviation_pct,
       70::numeric AS lagging_power_factor_below_pct,
       20::numeric AS minimum_pf_review_usage_kwh,
       'phase5_candidate_rules_v1'::text AS rule_version
FROM measures AS m;
