CREATE OR REPLACE VIEW analytics.energy_rule_summary AS
WITH rule_types(rule_type) AS (
    VALUES ('consumption_deviation'::text), ('lagging_power_factor_review'::text)
), hourly AS (
    SELECT count(*)::integer AS observed_hours,
           count(*) FILTER (WHERE eligible)::integer AS eligible_hours,
           count(*) FILTER (WHERE NOT eligible)::integer AS excluded_hours,
           count(*) FILTER (WHERE combined_priority)::integer AS combined_priority_hours,
           count(*) FILTER (WHERE consumption_deviation_candidate)::integer AS consumption_positive_hours,
           count(*) FILTER (WHERE lagging_power_factor_review_candidate)::integer AS pf_positive_hours
    FROM analytics.energy_rule_evaluation
), incidents AS (
    SELECT rule_type, count(*)::integer AS sustained_incident_count,
           coalesce(sum(observed_hour_count), 0)::integer AS sustained_candidate_hours
    FROM analytics.energy_candidate_incidents GROUP BY rule_type
)
SELECT r.rule_type, h.observed_hours, h.eligible_hours, h.excluded_hours,
       CASE r.rule_type WHEN 'consumption_deviation' THEN h.consumption_positive_hours
            ELSE h.pf_positive_hours END AS condition_positive_hours,
       coalesce(i.sustained_incident_count, 0) AS sustained_incident_count,
       coalesce(i.sustained_candidate_hours, 0) AS sustained_candidate_hours,
       h.combined_priority_hours, 'phase5_candidate_rules_v1'::text AS rule_version
FROM rule_types AS r CROSS JOIN hourly AS h
LEFT JOIN incidents AS i USING (rule_type);
