import logging
from typing import Dict, Any, Optional

try:
    from transitions import Machine
    HAS_TRANSITIONS = True
except ImportError:
    HAS_TRANSITIONS = False

try:
    from backend.extractor import extract_fields
    from backend.comparator import compare_history
    from backend.calculator import run_calculations
    from backend.assessor import assess_performance_and_risk
    from backend.recommender import make_recommendation
except ImportError:
    from extractor import extract_fields
    from comparator import compare_history
    from calculator import run_calculations
    from assessor import assess_performance_and_risk
    from recommender import make_recommendation

logger = logging.getLogger("RenewalStateMachine")

STATES = [
    "IDLE",
    "INTAKE",
    "EXTRACT",
    "COMPARE",
    "CALCULATE",
    "ASSESS",
    "RECOMMEND",
    "BRIEF_READY",
    "ERROR"
]

TRANSITIONS = [
    {"trigger": "load_case", "source": "IDLE", "dest": "INTAKE"},
    {"trigger": "validation_passed", "source": "INTAKE", "dest": "EXTRACT"},
    {"trigger": "validation_failed", "source": "INTAKE", "dest": "ERROR"},
    {"trigger": "extraction_done", "source": "EXTRACT", "dest": "COMPARE"},
    {"trigger": "comparison_done", "source": "COMPARE", "dest": "CALCULATE"},
    {"trigger": "calculation_done", "source": "CALCULATE", "dest": "ASSESS"},
    {"trigger": "assessment_done", "source": "ASSESS", "dest": "RECOMMEND"},
    {"trigger": "recommendation_done", "source": "RECOMMEND", "dest": "BRIEF_READY"},
    {"trigger": "error_occurred", "source": "*", "dest": "ERROR"},
]

class RenewalStateMachine:
    def __init__(self):
        self.state = "IDLE"
        self.raw_data: Optional[Dict[str, Any]] = None
        self.extracted: Dict[str, Any] = {}
        self.comparison: Dict[str, Any] = {}
        self.calculations: Dict[str, Any] = {}
        self.assessment: Dict[str, Any] = {}
        self.brief: Dict[str, Any] = {}
        self.error_message: Optional[str] = None
        self.state_history = []

        if HAS_TRANSITIONS:
            self.machine = Machine(
                model=self,
                states=STATES,
                transitions=TRANSITIONS,
                initial="IDLE",
                after_state_change="record_state"
            )
        else:
            self.record_state()

    def record_state(self):
        self.state_history.append(self.state)

    # Fallback trigger methods if transitions is not present
    if not HAS_TRANSITIONS:
        def load_case(self):
            self.state = "INTAKE"
            self.record_state()
        def validation_passed(self):
            self.state = "EXTRACT"
            self.record_state()
        def validation_failed(self):
            self.state = "ERROR"
            self.record_state()
        def extraction_done(self):
            self.state = "COMPARE"
            self.record_state()
        def comparison_done(self):
            self.state = "CALCULATE"
            self.record_state()
        def calculation_done(self):
            self.state = "ASSESS"
            self.record_state()
        def assessment_done(self):
            self.state = "RECOMMEND"
            self.record_state()
        def recommendation_done(self):
            self.state = "BRIEF_READY"
            self.record_state()
        def error_occurred(self):
            self.state = "ERROR"
            self.record_state()

    def _validate(self, data: Dict[str, Any]) -> bool:
        required_keys = [
            "case_id", "vendor", "msa", "current_pricing",
            "vendor_proposal", "sla", "usage", "renewal_history"
        ]
        return all(k in data for k in required_keys)

    def run(self, raw_json: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 1. INTAKE
            self.load_case()
            self.raw_data = raw_json
            if not self._validate(raw_json):
                self.validation_failed()
                return self._error_brief("Validation failed: Missing essential contract sections in raw JSON")
            self.validation_passed()

            # 2. EXTRACT
            self.extracted = extract_fields(self.raw_data)
            self.extraction_done()

            # 3. COMPARE
            self.comparison = compare_history(self.raw_data)
            self.comparison_done()

            # 4. CALCULATE
            self.calculations = run_calculations(self.extracted, self.comparison)
            self.calculation_done()

            # 5. ASSESS
            self.assessment = assess_performance_and_risk(self.extracted, self.calculations)
            self.assessment_done()

            # 6. RECOMMEND
            recommendation = make_recommendation(self.assessment, self.calculations)
            self.recommendation_done()

            # 7. BUILD SLIM BRIEF JSON (Only fields needed by the executive brief)
            self.brief = self._build_brief(recommendation)
            return self.brief

        except Exception as e:
            logger.exception("Error executing state machine")
            self.error_occurred()
            return self._error_brief(str(e))

    def _build_brief(self, recommendation: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "meta": {
                "case_id": self.raw_data.get("case_id", "UNKNOWN"),
                "assessment_date": self.extracted.get("assessment_date"),
                "renewal_deadline": self.extracted.get("renewal_deadline"),
                "notice_deadline": self.extracted.get("notice_deadline"),
                "notice_days": self.extracted.get("notice_days", 60),
                "notice_at_risk": self.calculations.get("notice_at_risk", False),
                "decision": recommendation.get("decision", "Renegotiate"),
                "confidentiality": "CONFIDENTIAL · EXECUTIVE BRIEF",
                "state_machine_audit": self.state_history
            },
            "vendor": {
                "name": self.extracted.get("vendor_name"),
                "service": self.extracted.get("service_type"),
                "proposed_term_months": self.extracted.get("proposed_term_months"),
                "account_manager": self.extracted.get("account_manager")
            },
            "financials": {
                "current_acv": self.extracted.get("current_acv"),
                "proposed_acv": self.extracted.get("proposed_acv"),
                "increase_pct": self.calculations.get("increase_pct"),
                "increase_usd": self.calculations.get("increase_usd"),
                "negotiation_target_acv": self.calculations.get("negotiation_target_acv"),
                "three_year_baseline": self.calculations.get("three_year_baseline"),
                "three_year_proposal": self.calculations.get("three_year_proposal"),
                "three_year_target": self.calculations.get("three_year_target"),
                "approved_budget_acv": self.extracted.get("approved_budget_acv"),
                "budget_gap_usd": self.calculations.get("budget_gap_usd")
            },
            "seats": {
                "total": self.extracted.get("total_seats"),
                "active": self.extracted.get("active_seats"),
                "inactive": self.extracted.get("inactive_seats"),
                "utilization_pct": self.calculations.get("utilization_pct"),
                "recommended_seats": self.calculations.get("recommended_seats"),
                "reduction_opportunity": self.calculations.get("reduction_opportunity"),
                "annualized_exposure_usd": self.calculations.get("seat_exposure_usd"),
                "current_unit_price": self.extracted.get("current_unit_price"),
                "proposed_unit_price": self.extracted.get("proposed_unit_price")
            },
            "history_trend": {
                "previous_increases": self.comparison.get("previous_increases", []),
                "avg_historical_increase_pct": self.comparison.get("avg_historical_increase_pct"),
                "total_spend_to_date": self.comparison.get("total_spend_to_date"),
                "current_increase_vs_avg": self.comparison.get("current_vs_avg_pct")
            },
            "performance": {
                "overall_rating": self.assessment.get("performance_rating"),
                "uptime_contracted": self.extracted.get("contracted_uptime"),
                "uptime_actual": self.extracted.get("actual_uptime"),
                "uptime_gap_pct": self.calculations.get("uptime_gap"),
                "support_sla_pct": self.extracted.get("support_sla_achievement"),
                "critical_incidents": self.extracted.get("critical_incidents_count"),
                "service_credits_unclaimed_usd": self.extracted.get("service_credits_available"),
                "roadmap_delivered": self.calculations.get("roadmap_delivered_count"),
                "roadmap_total": self.calculations.get("roadmap_total_count"),
                "roadmap_delayed": self.calculations.get("roadmap_delayed"),
                "key_observations": self.assessment.get("performance_observations", [])
            },
            "risks": {
                "overall_level": self.assessment.get("risk_level"),
                "items": self.assessment.get("risk_items", []),
                "critical_concern": self.assessment.get("critical_concern")
            },
            "recommendation": {
                "primary": recommendation.get("decision"),
                "rationale": recommendation.get("rationale"),
                "options": recommendation.get("options", []),
                "negotiation_objectives": recommendation.get("negotiation_objectives", []),
                "fallback": recommendation.get("fallback")
            },
            "timeline": self.extracted.get("timeline", {}),
            "further_analysis": self.assessment.get("further_analysis", []),
            "sla_addendum_flags": self.assessment.get("sla_addendum_flags", [])
        }

    def _error_brief(self, msg: str = "Validation failed") -> Dict[str, Any]:
        return {
            "error": True,
            "state": self.state,
            "message": msg,
            "state_history": self.state_history
        }
