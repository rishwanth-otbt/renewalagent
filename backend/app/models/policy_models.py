"""
Renewal policy: every threshold the moves use to decide.

The policy belongs to the client. It is versioned by the policy store and travels
with each run in the Dossier, so a brief can say which rule decided its label.
Defaults equal the values that used to be hard-coded in the moves.

Each field carries display metadata (label, unit, help, choices) used by the
settings page; `policy_field_catalog()` turns it into a list for the API.
"""
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _f(default: Any, label: str, help: str, unit: str, choices: List[Any], **kw) -> Any:
    """Field with settings-page metadata. `choices` are the dropdown options shown in the UI."""
    return Field(default, title=label, description=help,
                 json_schema_extra={"unit": unit, "choices": choices}, **kw)


class _Group(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


PCT = "%"


class RenewPolicy(_Group):
    """A proposal is a clean Renew only when every one of these holds."""
    max_increase_pct: float = _f(
        5.0, "Renew when the increase is at most", "Largest price increase that can still be renewed as-is.",
        PCT, [0.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0], ge=0, le=100)
    min_performance_rating: Literal["Good", "Acceptable"] = _f(
        "Good", "Minimum performance rating", "Lowest supplier rating (from M04) that can still be renewed as-is.",
        "", ["Good", "Acceptable"])
    require_within_budget: bool = _f(
        True, "Must be within approved budget", "Block Renew when the proposal is above the approved budget.",
        "", [True, False])
    require_within_price_cap: bool = _f(
        True, "Must respect the contract price cap", "Block Renew when the increase breaches the MSA price-increase cap.",
        "", [True, False])


class SwitchPolicy(_Group):
    """When to recommend Switch / Benchmark, and when switching is too costly."""
    price_shock_pct: float = _f(
        30.0, "Switch when the increase is at least", "Price increase that triggers a Switch / Benchmark on its own.",
        PCT, [15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0], ge=0, le=500)
    poor_performance_uptime_gap: float = _f(
        0.5, "…or uptime gap above", "Uptime shortfall (contracted minus actual, in points) that, with a Needs Improvement rating "
        "and a large increase, triggers a switch.", "pts", [0.2, 0.3, 0.5, 0.75, 1.0], gt=0, le=100)
    poor_performance_min_increase_pct: float = _f(
        20.0, "…together with an increase of at least", "Increase that, with poor performance, triggers a switch.",
        PCT, [10.0, 15.0, 20.0, 25.0], ge=0, le=500)
    hard_to_replace_levels: List[str] = _f(
        ["high", "very high", "critical"], "Hard-to-replace difficulty levels",
        "Replacement-difficulty values that make a vendor hard to replace.", "",
        [["high", "very high", "critical"], ["very high", "critical"], ["medium", "high", "very high", "critical"]])
    long_migration_months: int = _f(
        12, "Hard to replace when migration takes at least", "Migration estimate that makes a vendor hard to replace.",
        "months", [6, 9, 12, 18, 24], ge=1, le=120)

    @field_validator("hard_to_replace_levels")
    @classmethod
    def _levels(cls, v: List[str]) -> List[str]:
        levels = [s.strip().lower() for s in v if s.strip()]
        if not levels:
            raise ValueError("list at least one replacement-difficulty level")
        return levels


class BudgetPolicy(_Group):
    no_budget_target_uplift_pct: float = _f(
        3.0, "Target uplift when no budget is approved", "Negotiation target = current ACV plus this % when there is no approved budget.",
        PCT, [0.0, 2.0, 3.0, 4.0, 5.0], ge=0, le=100)


class PerformancePolicy(_Group):
    """M04 rating: Needs Improvement if ANY poor limit is crossed; Good if ALL good limits hold; else Acceptable."""
    poor_uptime_gap: float = _f(
        0.15, "Needs Improvement when uptime gap is above", "Contracted minus actual uptime, in percentage points.",
        "pts", [0.1, 0.15, 0.2, 0.25, 0.5], ge=0, le=100)
    poor_support_sla_pct: float = _f(
        75.0, "…or support SLA is below", "Support SLA achievement below this is poor.", PCT,
        [60.0, 70.0, 75.0, 80.0, 85.0], ge=0, le=100)
    poor_incidents: int = _f(
        3, "…or critical incidents reach", "Number of critical incidents that makes performance poor.", "incidents",
        [1, 2, 3, 4, 5], ge=1, le=1000)
    good_uptime_gap: float = _f(
        0.05, "Good when uptime gap is at most", "Largest uptime shortfall still rated Good.", "pts",
        [0.0, 0.02, 0.05, 0.1], ge=0, le=100)
    good_support_sla_pct: float = _f(
        90.0, "…and support SLA is at least", "Support SLA achievement needed for a Good rating.", PCT,
        [85.0, 90.0, 95.0, 98.0], ge=0, le=100)
    good_max_incidents: int = _f(
        0, "…and critical incidents are at most", "Most critical incidents still rated Good.", "incidents",
        [0, 1, 2], ge=0, le=1000)

    @model_validator(mode="after")
    def _order(self):
        errs = []
        if self.good_uptime_gap >= self.poor_uptime_gap:
            errs.append(f"performance: good uptime gap ({self.good_uptime_gap}) must be below the poor uptime gap ({self.poor_uptime_gap})")
        if self.poor_support_sla_pct >= self.good_support_sla_pct:
            errs.append(f"performance: poor support SLA ({self.poor_support_sla_pct}%) must be below the good support SLA ({self.good_support_sla_pct}%)")
        if self.good_max_incidents >= self.poor_incidents:
            errs.append(f"performance: good max incidents ({self.good_max_incidents}) must be below the poor incident count ({self.poor_incidents})")
        if errs:
            raise ValueError("; ".join(errs))
        return self


class LicensePolicy(_Group):
    target_utilization_pct: float = _f(
        90.0, "Shelfware when utilization is below", "Seat utilization (active in 90 days ÷ provisioned) below this is shelfware.",
        PCT, [70.0, 75.0, 80.0, 85.0, 90.0, 95.0], gt=0, le=100)
    seat_buffer_pct: float = _f(
        9.0, "Right-sizing buffer above active seats", "Recommended seats = active seats plus this % headroom.",
        PCT, [0.0, 5.0, 9.0, 10.0, 15.0, 20.0], ge=0, le=100)
    activity_window_days: int = _f(
        90, "Activity window", "Days of activity that count a seat as active (wording only; usage data is 90-day).",
        "days", [30, 60, 90], ge=1, le=365)


class DeadlinePolicy(_Group):
    urgent_notice_days: int = _f(
        21, "Notice is urgent within", "Days before the notice cutoff at which it becomes an imminent risk.",
        "days", [7, 14, 21, 30, 45, 60], ge=0, le=365)


class RiskPolicy(_Group):
    medium_increase_pct: float = _f(
        10.0, "Price-increase risk from", "Increase that is logged as a Medium price risk.", PCT,
        [5.0, 8.0, 10.0, 12.0], ge=0, le=500)
    high_increase_pct: float = _f(
        15.0, "High price-increase risk from", "Increase that is logged as a High price risk.", PCT,
        [10.0, 12.0, 15.0, 20.0], ge=0, le=500)
    severe_increase_pct: float = _f(
        25.0, "Severe price-escalation risk from", "Increase that is logged as severe escalation.", PCT,
        [20.0, 25.0, 30.0, 40.0], ge=0, le=500)
    long_term_months: int = _f(
        36, "Long term lock-in from", "Proposed term length that counts as a lock-in risk.", "months",
        [24, 36, 48, 60], ge=1, le=240)
    roadmap_backlog_count: int = _f(
        2, "Roadmap backlog risk from", "Undelivered roadmap items that count as a delivery risk.", "items",
        [1, 2, 3, 4], ge=1, le=100)
    high_items_for_high_level: int = _f(
        2, "Overall risk High from", "Number of High risk items that makes overall risk High.", "items",
        [1, 2, 3], ge=1, le=100)

    @model_validator(mode="after")
    def _order(self):
        if not (self.medium_increase_pct <= self.high_increase_pct <= self.severe_increase_pct):
            raise ValueError(
                f"risk: price-increase levels must rise: medium ({self.medium_increase_pct}%) ≤ high "
                f"({self.high_increase_pct}%) ≤ severe ({self.severe_increase_pct}%)")
        return self


class NegotiationPolicy(_Group):
    """Standard asks written into negotiation objectives."""
    seat_flex_pct: float = _f(
        10.0, "Ask for annual seat flexibility of ±", "Seat volume adjustment requested in every renegotiation.", PCT,
        [5.0, 10.0, 15.0, 20.0], ge=0, le=100)
    future_price_cap_pct: float = _f(
        3.0, "Ask for a future price cap of", "Maximum annual escalation requested for future cycles.", PCT,
        [2.0, 3.0, 4.0, 5.0], ge=0, le=100)
    bridge_term_months: int = _f(
        12, "Bridge term to ask for", "Length of a bridge extension when notice was missed.", "months",
        [3, 6, 12], ge=1, le=60)
    transition_assistance_months: int = _f(
        6, "Transition assistance to ask for", "Exit assistance period requested when switching.", "months",
        [3, 6, 9, 12], ge=1, le=60)


class RenewalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    renew: RenewPolicy = Field(default_factory=RenewPolicy, title="Renew")
    switch: SwitchPolicy = Field(default_factory=SwitchPolicy, title="Switch / Benchmark")
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy, title="Budget")
    performance: PerformancePolicy = Field(default_factory=PerformancePolicy, title="Supplier performance")
    licenses: LicensePolicy = Field(default_factory=LicensePolicy, title="Licenses")
    deadlines: DeadlinePolicy = Field(default_factory=DeadlinePolicy, title="Deadlines")
    risk: RiskPolicy = Field(default_factory=RiskPolicy, title="Risk register")
    negotiation: NegotiationPolicy = Field(default_factory=NegotiationPolicy, title="Negotiation asks")

    @model_validator(mode="after")
    def _cross_group(self):
        errs = []
        if self.renew.max_increase_pct >= self.switch.price_shock_pct:
            errs.append(f"renew limit ({self.renew.max_increase_pct}%) must be below the switch trigger ({self.switch.price_shock_pct}%)")
        if self.switch.poor_performance_min_increase_pct > self.switch.price_shock_pct:
            errs.append(f"switch: the poor-performance increase ({self.switch.poor_performance_min_increase_pct}%) "
                        f"must not exceed the price-shock trigger ({self.switch.price_shock_pct}%)")
        if errs:
            raise ValueError("; ".join(errs))
        return self


def policy_field_catalog() -> List[Dict[str, Any]]:
    """Settings-page metadata: one entry per group with its fields, labels, units, help and choices."""
    defaults = RenewalPolicy()
    groups = []
    for gkey, gfield in RenewalPolicy.model_fields.items():
        gmodel = gfield.annotation
        fields = []
        for fkey, f in gmodel.model_fields.items():
            extra = f.json_schema_extra or {}
            fields.append({
                "key": fkey,
                "label": f.title,
                "help": f.description,
                "unit": extra.get("unit", ""),
                "choices": extra.get("choices", []),
                "default": getattr(getattr(defaults, gkey), fkey),
            })
        groups.append({"key": gkey, "title": gfield.title, "description": (gmodel.__doc__ or "").strip(), "fields": fields})
    return groups
