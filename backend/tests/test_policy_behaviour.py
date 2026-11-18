"""M1 behaviour: rule boundaries under the default policy, and results that move when the policy changes."""
import copy
from datetime import date, timedelta

import pytest

from app.core.orchestrator import RenewalAgentOrchestrator
from app.models.policy_models import RenewalPolicy
from tests.conftest import AS_OF, DATA_DIR, SAMPLES_DIR, load_json

CLEAN = load_json(SAMPLES_DIR / "01_expect_renew_clean_good_performance_within_budget.json")  # ACV 250,000, cap 6%, budget 275,000


def run(raw, policy=None, as_of=AS_OF):
    return RenewalAgentOrchestrator().run_play(raw, as_of=as_of, policy=policy or RenewalPolicy())["brief"]


def with_proposal(acv):
    raw = copy.deepcopy(CLEAN)
    raw["vendor_proposal"]["proposed_annual_value"] = acv
    raw["vendor_proposal"]["proposed_unit_price"] = acv / raw["vendor_proposal"]["proposed_seats"]
    return raw


# --- Boundaries (default policy) -------------------------------------------------

@pytest.mark.parametrize("acv, pct, decision", [
    (262_500, 5.0, "Renew"),
    (262_750, 5.1, "Renegotiate"),
    (324_750, 29.9, "Renegotiate"),
    (325_000, 30.0, "Switch / Benchmark"),
])
def test_increase_boundaries(acv, pct, decision):
    brief = run(with_proposal(acv))
    assert brief["financials"]["increase_pct"] == pct
    assert brief["recommendation"]["primary"] == decision


@pytest.mark.parametrize("active, shelfware", [(900, False), (899, True)])
def test_utilization_boundary(active, shelfware):
    raw = copy.deepcopy(CLEAN)
    raw["usage"]["active_seats_last_90_days"] = active
    brief = run(raw)
    assert (brief["seats"]["reduction_opportunity"] > 0) is shelfware
    rule = "Underutilized licenses"
    assert any(r["risk"].startswith(rule) for r in brief["risks"]["items"]) is shelfware


@pytest.mark.parametrize("days_left, status", [(21, "IMMINENT_RISK"), (22, "ADEQUATE_RUNWAY"), (0, "IMMINENT_RISK")])
def test_notice_window_boundary(days_left, status):
    cutoff = date(2027, 9, 30) - timedelta(days=60)
    brief = run(CLEAN, as_of=cutoff - timedelta(days=days_left))
    assert brief["meta"]["days_to_notice"] == days_left
    assert brief["meta"]["notice_status"] == status


# --- Policy changes move the results ---------------------------------------------

CASE_001 = load_json(DATA_DIR / "renewal_input_001.json")  # +20%, Needs Improvement, over budget


def test_switch_trigger_20_makes_case_001_switch():
    assert run(CASE_001)["recommendation"]["primary"] == "Renegotiate"
    brief = run(CASE_001, RenewalPolicy.model_validate({"switch": {"price_shock_pct": 20}}))
    assert brief["recommendation"]["primary"] == "Switch / Benchmark"
    assert not next(c for c in brief["meta"]["rule_checks"] if c["id"] == "switch.price_shock_pct")["passed"]


def test_renew_limit_25_keeps_case_001_renegotiate_because_rating_and_budget_fail():
    brief = run(CASE_001, RenewalPolicy.model_validate({"renew": {"max_increase_pct": 25}}))
    assert brief["recommendation"]["primary"] == "Renegotiate"
    failed = {c["id"] for c in brief["meta"]["rule_checks"] if not c["passed"]}
    assert failed == {"renew.min_performance_rating", "renew.require_within_budget"}


def test_renew_at_7_percent_changes_result_without_code_change():
    """M1 'Done when': changing Renew at <= 7% changes results."""
    raw = load_json(SAMPLES_DIR / "17_expect_renegotiate_6pct_default_policy_renew_with_7pct_policy.json")
    assert run(raw)["recommendation"]["primary"] == "Renegotiate"
    brief = run(raw, RenewalPolicy.model_validate({"renew": {"max_increase_pct": 7}}))
    assert brief["recommendation"]["primary"] == "Renew"
    assert "within the 7% renew limit" in brief["recommendation"]["rationale"]


def test_performance_thresholds_change_rating():
    raw = load_json(SAMPLES_DIR / "18_expect_renegotiate_switch_downgraded_hard_to_replace_acceptable_performance.json")
    assert run(raw)["performance"]["overall_rating"] == "Acceptable"
    strict = RenewalPolicy.model_validate({"performance": {"poor_support_sla_pct": 86, "good_support_sla_pct": 95}})
    brief = run(raw, strict)
    assert brief["performance"]["overall_rating"] == "Needs Improvement"
    # Needs Improvement means the hard-to-replace downgrade no longer applies
    assert brief["recommendation"]["primary"] == "Switch / Benchmark"


def test_utilization_target_and_buffer_change_right_sizing():
    brief = run(CLEAN, RenewalPolicy.model_validate({"licenses": {"target_utilization_pct": 97, "seat_buffer_pct": 0}}))
    assert brief["seats"]["recommended_seats"] == 950
    assert brief["meta"]["success_criteria"][-1]["target"] == ">= 97% seat utilization"


def test_urgent_notice_window_from_policy():
    cutoff = date(2027, 9, 30) - timedelta(days=60)
    as_of = cutoff - timedelta(days=40)
    assert run(CLEAN, as_of=as_of)["meta"]["notice_status"] == "ADEQUATE_RUNWAY"
    brief = run(CLEAN, RenewalPolicy.model_validate({"deadlines": {"urgent_notice_days": 45}}), as_of=as_of)
    assert brief["meta"]["notice_status"] == "IMMINENT_RISK"


def test_minimum_rating_acceptable_allows_renew():
    raw = copy.deepcopy(CLEAN)
    raw["sla"]["actual_support_sla_achievement_pct"] = 85.0   # Acceptable
    assert run(raw)["recommendation"]["primary"] == "Renegotiate"
    brief = run(raw, RenewalPolicy.model_validate({"renew": {"min_performance_rating": "Acceptable"}}))
    assert brief["recommendation"]["primary"] == "Renew"


def test_budget_rule_can_be_switched_off():
    raw = load_json(SAMPLES_DIR / "03_expect_renegotiate_over_budget_small_increase_no_price_cap.json")
    assert run(raw)["recommendation"]["primary"] == "Renegotiate"
    brief = run(raw, RenewalPolicy.model_validate({"renew": {"require_within_budget": False}}))
    assert brief["recommendation"]["primary"] == "Renew"
    assert "over budget (allowed by policy)" in brief["recommendation"]["rationale"]


def test_no_budget_target_uplift_from_policy():
    raw = load_json(SAMPLES_DIR / "20_expect_renegotiate_no_approved_budget_target_current_plus_3pct.json")
    assert run(raw)["financials"]["negotiation_target_acv"] == 257_500.0
    brief = run(raw, RenewalPolicy.model_validate({"budget": {"no_budget_target_uplift_pct": 0}}))
    assert brief["financials"]["negotiation_target_acv"] == 250_000.0


def test_negotiation_asks_from_policy():
    pol = RenewalPolicy.model_validate({"negotiation": {"seat_flex_pct": 15, "future_price_cap_pct": 2}})
    objectives = run(CASE_001, pol)["recommendation"]["negotiation_objectives"]
    assert any("±15%" in o for o in objectives)
    assert any("maximum 2% annual escalation" in o for o in objectives)
