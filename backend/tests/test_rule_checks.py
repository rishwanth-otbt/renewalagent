"""Every brief states the policy version and the rules that decided its label."""
import pytest

from app.core.orchestrator import RenewalDeskOrchestrator
from app.models.policy_models import RenewalPolicy
from tests.conftest import AS_OF, case_key, load_json, valid_case_files

RULE_IDS = ["renew.max_increase_pct", "renew.min_performance_rating", "renew.require_within_budget",
            "renew.require_within_price_cap", "switch.price_shock_pct", "switch.poor_performance",
            "switch.hard_to_replace"]


@pytest.mark.parametrize("path", valid_case_files(), ids=case_key)
def test_brief_explains_decision(path):
    brief = RenewalDeskOrchestrator().run_play(load_json(path), as_of=AS_OF, policy=RenewalPolicy(), policy_version=0)["brief"]
    meta = brief["meta"]
    decision = brief["recommendation"]["primary"]
    checks = {c["id"]: c for c in meta["rule_checks"]}

    assert meta["policy_version"] == 0
    assert meta["policy"] == RenewalPolicy().model_dump()
    assert list(checks) == RULE_IDS
    for c in checks.values():
        assert c["rule"] and c["limit"] and c["actual"] and isinstance(c["passed"], bool)
    assert meta["decided_by"].startswith(decision)

    renew_ok = all(c["passed"] for c in checks.values() if c["group"] == "Renew")
    switch_fired = not all(c["passed"] for c in checks.values() if c["group"] == "Switch")
    if decision == "Renew":
        assert renew_ok and not switch_fired
    elif decision == "Switch / Benchmark":
        assert switch_fired
    else:
        assert not renew_ok or brief["recommendation"]["switch_downgraded"]
