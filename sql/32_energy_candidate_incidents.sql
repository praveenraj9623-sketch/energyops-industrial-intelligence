-- Independent rule streams; a non-positive, excluded or absent hour breaks continuity.
CREATE OR REPLACE VIEW analytics.energy_candidate_incidents AS
WITH streams AS (
    SELECT 'consumption_deviation'::text AS rule_type, c.*
    FROM analytics.energy_candidate_hours AS c
    WHERE c.consumption_deviation_candidate IS TRUE
    UNION ALL
    SELECT 'lagging_power_factor_review'::text AS rule_type, c.*
    FROM analytics.energy_candidate_hours AS c
    WHERE c.lagging_power_factor_review_candidate IS TRUE
), prior AS (
    SELECT s.*, lag(s.hour_start_local) OVER
           (PARTITION BY s.rule_type ORDER BY s.hour_start_local) AS prior_candidate_hour_local
    FROM streams AS s
), starts AS (
    SELECT p.*, CASE WHEN p.prior_candidate_hour_local = p.hour_start_local - INTERVAL '1 hour'
                    THEN 0 ELSE 1 END AS island_start
    FROM prior AS p
), islands AS (
    SELECT s.*, sum(s.island_start) OVER
           (PARTITION BY s.rule_type ORDER BY s.hour_start_local
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS island_number
    FROM starts AS s
), grouped AS (
    SELECT rule_type, min(hour_start_local) AS start_hour_local,
           max(hour_start_local) AS last_candidate_hour_local,
           count(*)::integer AS observed_hour_count,
           max(observed_usage_kwh) AS peak_observed_usage_kwh,
           max(greatest(excess_kwh, 0)) AS peak_positive_excess_kwh,
           max(deviation_pct) AS peak_signed_deviation_pct,
           min(mean_lagging_power_factor_pct) AS minimum_mean_lagging_power_factor_pct,
           jsonb_agg(jsonb_build_object('hour_start_local', hour_start_local,
                        'load_type_components', load_type_component_evidence,
                        'combined_priority', combined_priority)
                     ORDER BY hour_start_local) AS hourly_load_type_context
    FROM islands
    GROUP BY rule_type, island_number
    HAVING count(*) >= 2
)
SELECT md5('phase5_candidate_rules_v1|' || rule_type || '|' ||
           to_char(start_hour_local, 'YYYY-MM-DD HH24:MI:SS')) AS incident_key,
       rule_type, start_hour_local, last_candidate_hour_local,
       observed_hour_count, observed_hour_count AS duration_observed_hours,
       peak_observed_usage_kwh, peak_positive_excess_kwh,
       peak_signed_deviation_pct, minimum_mean_lagging_power_factor_pct,
       hourly_load_type_context, 'candidate for review'::text AS status,
       'phase5_candidate_rules_v1'::text AS rule_version
FROM grouped;
