-- Grain: one row per exclusive eligibility status among observed hours.
CREATE OR REPLACE VIEW analytics.energy_hourly_eligibility_status AS
WITH grouped AS (
    SELECT coalesce(e.exclusion_reason, 'eligible') AS status,
           e.eligible,
           count(*)::integer AS hour_count
    FROM analytics.energy_hourly_baseline_eligibility AS e
    GROUP BY coalesce(e.exclusion_reason, 'eligible'), e.eligible
), total AS (
    SELECT sum(hour_count) AS observed_hour_count FROM grouped
)
SELECT g.status, g.eligible, g.hour_count,
       g.hour_count::numeric * 100 / NULLIF(t.observed_hour_count, 0) AS percentage_of_observed_hours
FROM grouped AS g CROSS JOIN total AS t;
