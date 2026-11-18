"""
Extracts the decision-relevant results of one run, used by the golden tests.

Only numbers, labels and rule outcomes are recorded, not free text, so wording
improvements do not break the safety net but any change in a result does.
"""
from typing import Any, Dict


def snapshot(brief: Dict[str, Any]) -> Dict[str, Any]:
    fin, seats, perf = brief["financials"], brief["seats"], brief["performance"]
    rec, risks, meta = brief["recommendation"], brief["risks"], brief["meta"]
    return {
        "decision": rec["primary"],
        "switch_downgraded": rec["switch_downgraded"],
        "risk_level": risks["overall_level"],
        "risk_items": [[r["risk"], r["level"]] for r in risks["items"]],
        "increase_pct": fin["increase_pct"],
        "budget_gap_usd": fin["budget_gap_usd"],
        "negotiation_target_acv": fin["negotiation_target_acv"],
        "three_year_target": fin["three_year_target"],
        "cap_breach": fin["cap_breach"],
        "performance_rating": perf["overall_rating"],
        "utilization_pct": seats["utilization_pct"],
        "recommended_seats": seats["recommended_seats"],
        "reduction_opportunity": seats["reduction_opportunity"],
        "renewal_type": meta["renewal_type"],
        "notice_status": meta["notice_status"],
        "n_objectives": len(rec["negotiation_objectives"]),
        "n_drivers": len(rec["drivers"]),
        "n_success_criteria": len(meta["success_criteria"]),
        "timeline_phases": len(brief["timeline"]["steps"]),
    }
