from typing import Dict, Any, List

def make_recommendation(assessment: Dict[str, Any], calculations: Dict[str, Any]) -> Dict[str, Any]:
    increase_pct = calculations.get("increase_pct", 0.0)
    perf_rating = assessment.get("performance_rating", "Acceptable")
    budget_gap = calculations.get("budget_gap_usd", 0.0)
    target_acv = calculations.get("negotiation_target_acv", 0.0)
    recommended_seats = calculations.get("recommended_seats", 0)
    reduction_opportunity = calculations.get("reduction_opportunity", 0)
    unclaimed_credits = assessment.get("sla_addendum_flags", [])
    
    # Extract service credit amount if available
    service_credit_val = 0.0
    for fl in unclaimed_credits:
        if fl.get("type") == "Unclaimed Service Credits":
            # e.g. "$48,000 in eligible..."
            detail = fl.get("detail", "")
            if "$" in detail:
                try:
                    num_str = detail.split("$")[1].split(" ")[0].replace(",", "")
                    service_credit_val = float(num_str)
                except Exception:
                    service_credit_val = 0.0

    # Decision Matrix:
    # 1. SWITCH / BENCHMARK: Severe escalation (>= 30%), or chronic failure (>= 5 critical outages with double-digit increase)
    if increase_pct >= 30.0 or (calculations.get("uptime_gap", 0) > 0.5 and perf_rating == "Needs Improvement" and increase_pct >= 20.0):
        decision = "Switch / Benchmark"
        rationale = (
            f"The vendor's +{increase_pct}% price increase is commercially unviable and creates a substantial "
            f"${budget_gap:,.0f} budget overrun. Combined with chronic SLA underperformance, an immediate "
            f"competitive RFP and notice of non-renewal is strongly warranted."
        )
        options: List[Dict[str, str]] = [
            {"option": "Renew as-is", "assessment": "Strongly Rejected (causes unacceptable budget deficit & condones poor SLA)"},
            {"option": "Renegotiate", "assessment": "Last Resort (only if vendor concedes to baseline pricing and strict SLA penalties)"},
            {"option": "Restructure licenses", "assessment": "Required if staying (reclaim unused seats immediately)"},
            {"option": "Benchmark alternatives", "assessment": "Mandatory (launch competitive market tender with short-listed alternatives)"},
            {"option": "Switch vendor immediately", "assessment": "Preferred / High Priority (initiate formal migration evaluation)"}
        ]
        objectives = [
            "Issue formal conditional Notice of Non-Renewal prior to contractual notice deadline to preserve exit rights.",
            f"Issue aggressive counter-target of ${target_acv:,.0f} ACV (rejecting the {increase_pct}% price hike completely).",
            f"If staying, cut license volume to {recommended_seats:,} seats (shedding {reduction_opportunity:,} unused seats).",
            "Incorporate a 6-month transition assistance SLA clause ensuring zero data-export or exit penalties.",
            "Parallel-track technical discovery with alternative platforms to demonstrate viable walk-away posture."
        ]
        fallback = (
            "If vendor refuses to roll back price increases to baseline and restore SLA commitments, execute migration "
            "plan to alternative vendor upon current contract expiration."
        )

    # 2. RENEW: Low inflation (<= 5%), stellar SLA, and within budget
    elif increase_pct <= 5.0 and perf_rating == "Good" and budget_gap <= 0:
        decision = "Renew"
        rationale = (
            f"Vendor continues to demonstrate strong operational excellence with high SLA achievement. "
            f"The proposed price adjustment of +{increase_pct}% is modest, falls within approved budget, "
            f"and locking in the proposed term provides commercial stability."
        )
        options: List[Dict[str, str]] = [
            {"option": "Renew as-is", "assessment": "Preferred (commercially fair and operationally stable)"},
            {"option": "Renegotiate", "assessment": "Optional (explore minor volume rebate or multi-year prepay discount)"},
            {"option": "Restructure licenses", "assessment": "Not required (adoption remains above 90% threshold)"},
            {"option": "Benchmark alternatives", "assessment": "Low priority (switching costs outweigh any marginal savings)"},
            {"option": "Switch vendor", "assessment": "Not recommended (high disruption risk for an already well-performing vendor)"}
        ]
        objectives = [
            f"Execute renewal at proposed ${calculations.get('three_year_proposal', 0) / 3:,.0f} ACV, locking in multi-year price protection.",
            "Verify that all current security, compliance, and support addenda automatically carry over.",
            "Include standard SLA protection guaranteeing >= 99.9% availability with financial remedies.",
            "Secure an annual true-up mechanism allowing license expansion at the same locked-in unit price."
        ]
        fallback = (
            "If vendor attempts last-minute commercial alterations, negotiate a 1-year bridge extension "
            "at the current rate before committing to a multi-year term."
        )

    # 3. RENEGOTIATE: Strategic vendor, but pricing hike or utilization waste requires commercial counter-attack
    else:
        decision = "Renegotiate"
        rationale = (
            f"Vendor remains functionally core, but proposed +{increase_pct}% increase exceeds performance delivery. "
            f"Underutilization ({reduction_opportunity:,} inactive seats) and SLA gaps "
            f"provide strong commercial leverage to counter-offer."
        )
        options: List[Dict[str, str]] = [
            {"option": "Renew as-is", "assessment": f"Not recommended (creates ${budget_gap:,.0f} budget gap & locks in shelfware)"},
            {"option": "Renegotiate", "assessment": f"Preferred (counter-target ${target_acv:,.0f} ACV with restructured seats)"},
            {"option": "Restructure licenses", "assessment": f"Recommended (right-size from {calculations.get('total_seats', 0):,} to {recommended_seats:,} seats)"},
            {"option": "Benchmark alternatives", "assessment": "Recommended (parallel evaluation to maintain negotiation leverage)"},
            {"option": "Switch vendor immediately", "assessment": "Not yet justified (migration overhead exceeds current savings potential)"}
        ]
        objectives = [
            f"Right-size license commitment to {recommended_seats:,} seats (releasing ~{reduction_opportunity:,} inactive licenses).",
            f"Reject the {increase_pct}% escalation and establish counter-target at ${target_acv:,.0f} ACV.",
            f"Apply eligible SLA outage penalty credits ({f'${service_credit_val:,.0f}' if service_credit_val > 0 else 'contractual remedies'}) against Year 1 invoicing.",
            "Institute enforceable service credit thresholds for future availability drops below contracted target.",
            "Introduce contract flexibility clause permitting annual ±10% seat volume adjustments.",
            "Secure price-protection cap (maximum 3% annual escalation) for future renewal cycles."
        ]
        fallback = (
            "If vendor rejects commercial restructuring and maintains the price hike, issue conditional notice of non-renewal "
            "prior to the notice cutoff, while fast-tracking an RFP with short-listed alternatives."
        )

    return {
        "decision": decision,
        "rationale": rationale,
        "options": options,
        "negotiation_objectives": objectives,
        "fallback": fallback
    }
