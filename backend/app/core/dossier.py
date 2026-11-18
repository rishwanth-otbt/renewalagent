"""
Central Dossier: Shared context and knowledge base populated sequentially by Moves.
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


@dataclass
class Dossier:
    # 0. Validated input (see RenewalInputData) and the run date.
    # Scalars start as None: a field no move has set shows up as null, never as a guess.
    raw_data: Dict[str, Any] = field(default_factory=dict)
    as_of: Optional[date] = None
    case_id: Optional[str] = None
    # Client policy in force for this run (RenewalPolicy). Every threshold a move uses comes from here.
    policy: Any = None
    policy_version: Optional[int] = None       # 0 = built-in defaults; None = unsaved draft (preview)
    rule_checks: List[Dict[str, Any]] = field(default_factory=list)  # rules that decided the label (M10 G1)

    # 1. Populated by M01 (Set Renewal Goals)
    decision_question: Optional[str] = None
    accountable_owner: Optional[str] = None
    approved_budget_acv: Optional[float] = None
    strategic_importance: Optional[str] = None
    known_alternatives: List[str] = field(default_factory=list)
    success_criteria: List[Dict[str, Any]] = field(default_factory=list)
    authorized_actions: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    m01_status: Optional[str] = None

    # 2. Populated by M02 (Check Agreement Terms)
    vendor_name: Optional[str] = None
    service_type: Optional[str] = None
    contract_id: Optional[str] = None
    current_term_months: Optional[int] = None
    proposed_term_months: Optional[int] = None
    current_acv: Optional[float] = None
    proposed_acv: Optional[float] = None
    current_unit_price: Optional[float] = None
    proposed_unit_price: Optional[float] = None
    termination_for_convenience: Optional[bool] = None
    auto_renewal: Optional[bool] = None
    addenda_flags: List[Dict[str, str]] = field(default_factory=list)

    # 3. Populated by M03 (Check Renewal Deadlines)
    renewal_deadline: Optional[str] = None
    notice_deadline: Optional[str] = None
    notice_period_days: Optional[int] = None
    days_to_notice: Optional[int] = None
    notice_at_risk: Optional[bool] = None      # 0..policy.deadlines.urgent_notice_days left before the cutoff
    notice_passed: Optional[bool] = None       # notice cutoff is already in the past
    notice_status: Optional[str] = None        # ADEQUATE_RUNWAY | IMMINENT_RISK | NOTICE_WINDOW_CLOSED | AUTO_RENEWED_LOCK_IN

    # 4. Populated by M04 (Assess Supplier Performance)
    contracted_uptime: Optional[float] = None
    actual_uptime: Optional[float] = None
    uptime_gap: Optional[float] = None
    support_sla_achievement: Optional[float] = None
    critical_incidents_count: Optional[int] = None
    service_credits_available: Optional[float] = None
    roadmap_delivered_count: Optional[int] = None
    roadmap_total_count: Optional[int] = None
    roadmap_delayed_features: List[str] = field(default_factory=list)
    performance_rating: Optional[str] = None
    performance_observations: List[str] = field(default_factory=list)

    # 5. Populated by M05 (Analyze Usage & License Needs)
    total_provisioned_seats: Optional[int] = None
    active_seats: Optional[int] = None
    inactive_seats: Optional[int] = None
    utilization_pct: Optional[float] = None
    has_shelfware: Optional[bool] = None
    recommended_seats: Optional[int] = None
    reduction_opportunity: Optional[int] = None
    annualized_waste_usd: Optional[float] = None
    proposed_seats: Optional[int] = None
    renewal_type: Optional[str] = None         # EXPANSION | REDUCTION | FLAT (seat volume vs current)
    seat_change: Optional[int] = None
    added_modules: List[str] = field(default_factory=list)
    removed_modules: List[str] = field(default_factory=list)

    # 6. Populated by M10 (Model Costs & Recommend)
    increase_usd: Optional[float] = None
    increase_pct: Optional[float] = None
    three_year_baseline: Optional[float] = None
    three_year_proposal: Optional[float] = None
    three_year_target: Optional[float] = None
    negotiation_target_acv: Optional[float] = None
    budget_gap_usd: Optional[float] = None
    price_cap_pct: Optional[float] = None
    cap_breach: Optional[bool] = None
    capped_acv: Optional[float] = None
    hard_to_replace: Optional[bool] = None
    switch_downgraded: Optional[bool] = None
    decision_drivers: List[str] = field(default_factory=list)
    historical_spend_to_date: Optional[float] = None
    historical_avg_increase_pct: Optional[float] = None
    current_vs_avg_increase_pct: Optional[float] = None
    previous_cycles: List[Dict[str, Any]] = field(default_factory=list)

    risk_level: Optional[str] = None
    risk_items: List[Dict[str, str]] = field(default_factory=list)
    critical_concern: Optional[str] = None
    primary_decision: Optional[str] = None
    decision_rationale: Optional[str] = None
    strategic_options: List[Dict[str, str]] = field(default_factory=list)
    negotiation_objectives: List[str] = field(default_factory=list)
    fallback_strategy: Optional[str] = None
    timeline: Dict[str, Any] = field(default_factory=dict)

    # Output Brief
    brief: Dict[str, Any] = field(default_factory=dict)
