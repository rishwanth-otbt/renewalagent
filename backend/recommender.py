from typing import Dict, Any, List

def make_recommendation(assessment: Dict[str, Any], calculations: Dict[str, Any]) -> Dict[str, Any]:
    increase_pct = calculations.get("increase_pct", 0.0)
    perf_rating = assessment.get("performance_rating", "Acceptable")
    budget_gap = calculations.get("budget_gap_usd", 0.0)
    target_acv = calculations.get("negotiation_target_acv", 0.0)
    recommended_seats = calculations.get("recommended_seats", 850)

    if increase_pct >= 15.0 or perf_rating == "Needs Improvement":
        decision = "Renegotiate"
        rationale = (
            f"Vendor remains functionally core, but proposed {increase_pct}% increase exceeds performance delivery. "
            f"Underutilization ({calculations.get('reduction_opportunity', 0)} inactive seats) and SLA infractions "
            "provide strong commercial leverage to counter-offer."
        )
    elif increase_pct <= 5.0 and perf_rating == "Good":
        decision = "Renew"
        rationale = "Commercial increase is modest and performance metrics consistently meet SLA expectations."
    else:
        decision = "Renegotiate"
        rationale = "Targeted negotiation required to optimize license tiering and align pricing with internal budget."

    options: List[Dict[str, str]] = [
        {"option": "Renew as-is", "assessment": "Not recommended (causes $190k budget overrun & locks in unused seats)"},
        {"option": "Renegotiate", "assessment": "Preferred (target $1.25M ACV with restructured seat count)"},
        {"option": "Restructure licenses", "assessment": "Recommended (right-size from 1,000 to 850 provisioned seats)"},
        {"option": "Benchmark alternatives", "assessment": "Recommended (parallel evaluation of market alternatives)"},
        {"option": "Switch vendor immediately", "assessment": "Not yet justified (migration overhead exceeds current savings potential)"}
    ]

    objectives = [
        f"Right-size license commitment to {recommended_seats:,} seats (releasing ~{calculations.get('reduction_opportunity', 0)} inactive licenses).",
        f"Reject the {increase_pct}% escalation and establish counter-target at ${target_acv:,.0f} ACV.",
        "Apply $48,000 in uncredited SLA downtime as an immediate credit towards Year 1 invoicing.",
        "Institute enforceable service credit thresholds for future availability drops below 99.9%.",
        "Introduce contract flexibility clause permitting annual ±10% seat volume adjustments.",
        "Secure price-protection cap (maximum 3% annual escalation) for future renewal cycles."
    ]

    fallback = (
        "If vendor rejects commercial restructuring and maintains the 20% price hike, issue conditional notice of non-renewal "
        "prior to the 60-day notice cutoff, while fast-tracking an RFP with short-listed alternatives."
    )

    return {
        "decision": decision,
        "rationale": rationale,
        "options": options,
        "negotiation_objectives": objectives,
        "fallback": fallback
    }
