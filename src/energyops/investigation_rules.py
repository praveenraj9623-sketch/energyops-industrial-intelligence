"""Fixed Phase 5 candidate rules and rerunnable view installation."""

from decimal import Decimal

from .config import PROJECT_ROOT

RULE_VERSION = "phase5_candidate_rules_v1"
MIN_EXCESS_KWH = Decimal("10")
MIN_DEVIATION_PCT = Decimal("30")
PF_BELOW_PCT = Decimal("70")
MIN_PF_USAGE_KWH = Decimal("20")
SQL_FILES = ("30_energy_rule_evaluation.sql", "31_energy_candidate_hours.sql",
             "32_energy_candidate_incidents.sql", "33_energy_rule_summary.sql")


def decide_hour(eligible: bool, observation_count: int, observed_kwh, expected_kwh,
                mean_lagging_pf_pct) -> dict:
    """Independent, NULL-safe formulation for verification and small fixtures."""
    ready = eligible and observation_count == 4 and observed_kwh is not None
    excess = observed_kwh - expected_kwh if observed_kwh is not None and expected_kwh is not None else None
    deviation = Decimal(100) * excess / expected_kwh if excess is not None and expected_kwh else None
    consumption = bool(ready and excess is not None and deviation is not None
                       and excess >= MIN_EXCESS_KWH and deviation >= MIN_DEVIATION_PCT)
    pf = bool(ready and mean_lagging_pf_pct is not None
              and mean_lagging_pf_pct < PF_BELOW_PCT and observed_kwh >= MIN_PF_USAGE_KWH)
    return {"excess_kwh": excess, "deviation_pct": deviation,
            "consumption_deviation_candidate": consumption,
            "lagging_power_factor_review_candidate": pf, "combined_priority": consumption and pf}


def apply_investigation_models(conn) -> None:
    with conn.transaction():
        for filename in SQL_FILES:
            conn.execute((PROJECT_ROOT / "sql" / filename).read_text(encoding="utf-8"))
