"""Policy model: defaults equal the old hard-coded values; contradictions are rejected with clear messages."""
import pytest
from pydantic import ValidationError

from app.models.policy_models import RenewalPolicy, policy_field_catalog


def test_defaults_equal_previous_hard_coded_values():
    p = RenewalPolicy()
    assert p.renew.max_increase_pct == 5.0
    assert p.switch.price_shock_pct == 30.0
    assert (p.switch.poor_performance_uptime_gap, p.switch.poor_performance_min_increase_pct) == (0.5, 20.0)
    assert p.switch.hard_to_replace_levels == ["high", "very high", "critical"]
    assert p.switch.long_migration_months == 12
    assert p.budget.no_budget_target_uplift_pct == 3.0
    assert (p.performance.poor_uptime_gap, p.performance.poor_support_sla_pct, p.performance.poor_incidents) == (0.15, 75.0, 3)
    assert (p.performance.good_uptime_gap, p.performance.good_support_sla_pct, p.performance.good_max_incidents) == (0.05, 90.0, 0)
    assert (p.licenses.target_utilization_pct, p.licenses.seat_buffer_pct) == (90.0, 9.0)
    assert p.deadlines.urgent_notice_days == 21


def _err(data) -> str:
    with pytest.raises(ValidationError) as exc:
        RenewalPolicy.model_validate(data)
    return str(exc.value)


@pytest.mark.parametrize("data, message", [
    ({"renew": {"max_increase_pct": 30}}, "renew limit (30.0%) must be below the switch trigger (30.0%)"),
    ({"switch": {"price_shock_pct": 4}}, "must be below the switch trigger"),
    ({"performance": {"poor_support_sla_pct": 90}}, "poor support SLA (90.0%) must be below the good support SLA (90.0%)"),
    ({"performance": {"good_uptime_gap": 0.2}}, "good uptime gap (0.2) must be below the poor uptime gap (0.15)"),
    ({"performance": {"good_max_incidents": 3}}, "good max incidents (3) must be below the poor incident count (3)"),
    ({"risk": {"high_increase_pct": 30}}, "price-increase levels must rise"),
    ({"switch": {"poor_performance_min_increase_pct": 35}}, "must not exceed the price-shock trigger"),
    ({"switch": {"hard_to_replace_levels": [" "]}}, "at least one replacement-difficulty level"),
    ({"renew": {"min_performance_rating": "Excellent"}}, "min_performance_rating"),
    ({"licenses": {"target_utilization_pct": 120}}, "target_utilization_pct"),
    ({"renew": {"unknown_rule": 1}}, "unknown_rule"),
])
def test_contradictory_or_invalid_policies_are_rejected(data, message):
    assert message in _err(data)


def test_partial_policy_fills_missing_values_from_defaults():
    p = RenewalPolicy.model_validate({"renew": {"max_increase_pct": 7}})
    assert p.renew.max_increase_pct == 7.0
    assert p.switch.price_shock_pct == 30.0


def test_catalog_covers_every_field_with_its_default():
    catalog = policy_field_catalog()
    dumped = RenewalPolicy().model_dump()
    assert [g["key"] for g in catalog] == list(dumped)
    for g in catalog:
        assert [f["key"] for f in g["fields"]] == list(dumped[g["key"]])
        for f in g["fields"]:
            assert f["label"] and f["default"] == dumped[g["key"]][f["key"]]
            assert f["default"] in f["choices"], f"{g['key']}.{f['key']} default missing from choices"
