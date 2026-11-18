"""
Central Dossier: Shared context and knowledge base populated sequentially by Moves.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Dossier:
    # 0. Raw Input
    raw_data: Dict[str, Any] = field(default_factory=dict)
    case_id: str = "UNKNOWN"

    # 1. Populated by M01 (Set Renewal Goals)
    decision_question: str = ""
    accountable_owner: str = ""
    approved_budget_acv: float = 0.0
    strategic_importance: str = "Medium"
    known_alternatives: List[str] = field(default_factory=list)
    success_criteria: List[Dict[str, Any]] = field(default_factory=list)
    authorized_actions: List[str] = field(default_factory=list)
    exclusions: List[str] = field(default_factory=list)
    m01_status: str = "DRAFT"

    # 2. Populated by M02 (Check Agreement Terms)
    vendor_name: str = ""
    service_type: str = ""
    contract_id: str = ""
    current_term_months: int = 12
    proposed_term_months: int = 36
    current_acv: float = 0.0
    proposed_acv: float = 0.0
    current_unit_price: float = 0.0
    proposed_unit_price: float = 0.0
    termination_for_convenience: bool = False
    auto_renewal: bool = True
    addenda_flags: List[Dict[str, str]] = field(default_factory=list)

    # 3. Populated by M03 (Check Renewal Deadlines)
    renewal_deadline: str = ""
    notice_deadline: str = ""
    notice_period_days: int = 60
    days_to_notice: int = 0
    notice_at_risk: bool = False

    # 4. Populated by M04 (Assess Supplier Performance)
    contracted_uptime: float = 99.9
    actual_uptime: float = 99.9
    uptime_gap: float = 0.0
    support_sla_achievement: float = 100.0
    critical_incidents_count: int = 0
    service_credits_available: float = 0.0
    roadmap_delivered_count: int = 0
    roadmap_total_count: int = 0
    roadmap_delayed_features: List[str] = field(default_factory=list)
    performance_rating: str = "Acceptable"
    performance_observations: List[str] = field(default_factory=list)

    # 5. Populated by M05 (Analyze Usage & License Needs)
    total_provisioned_seats: int = 0
    active_seats: int = 0
    inactive_seats: int = 0
    utilization_pct: float = 100.0
    has_shelfware: bool = False
    recommended_seats: int = 0
    reduction_opportunity: int = 0
    annualized_waste_usd: float = 0.0

    # 6. Populated by M10 (Model Costs & Recommend)
    increase_usd: float = 0.0
    increase_pct: float = 0.0
    three_year_baseline: float = 0.0
    three_year_proposal: float = 0.0
    three_year_target: float = 0.0
    negotiation_target_acv: float = 0.0
    budget_gap_usd: float = 0.0
    historical_spend_to_date: float = 0.0
    historical_avg_increase_pct: float = 0.0
    current_vs_avg_increase_pct: float = 0.0
    previous_cycles: List[Dict[str, Any]] = field(default_factory=list)

    risk_level: str = "Medium"
    risk_items: List[Dict[str, str]] = field(default_factory=list)
    critical_concern: str = ""
    primary_decision: str = "Renegotiate"
    decision_rationale: str = ""
    strategic_options: List[Dict[str, str]] = field(default_factory=list)
    negotiation_objectives: List[str] = field(default_factory=list)
    fallback_strategy: str = ""
    timeline: Dict[str, Any] = field(default_factory=dict)

    # Output Brief
    brief: Dict[str, Any] = field(default_factory=dict)
