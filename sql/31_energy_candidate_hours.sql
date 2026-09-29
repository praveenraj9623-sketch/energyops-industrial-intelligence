CREATE OR REPLACE VIEW analytics.energy_candidate_hours AS
SELECT *
FROM analytics.energy_rule_evaluation
WHERE eligible IS TRUE
  AND (consumption_deviation_candidate IS TRUE
       OR lagging_power_factor_review_candidate IS TRUE);
