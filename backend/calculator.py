from datetime import datetime
from typing import Dict, Any

def run_calculations(extracted: Dict[str, Any], comparison: Dict[str, Any]) -> Dict[str, Any]:
    current_acv = extracted.get("current_acv", 0.0)
    proposed_acv = extracted.get("proposed_acv", 0.0)
    proposed_term_months = extracted.get("proposed_term_months", 36)
    proposed_unit_price = extracted.get("proposed_unit_price", 0.0)
    approved_budget_acv = extracted.get("approved_budget_acv", 0.0)
    
    total_seats = extracted.get("total_seats", 0)
    active_seats = extracted.get("active_seats", 0)

    # Financial calculations
    increase_usd = round(proposed_acv - current_acv, 2)
    increase_pct = round((increase_usd / current_acv * 100), 1) if current_acv > 0 else 0.0
    
    # Term baseline & proposal calculations
    three_year_baseline = round(current_acv * (proposed_term_months / 12.0), 2)
    three_year_proposal = round(proposed_acv * (proposed_term_months / 12.0), 2)
    
    # Negotiation target calculation:
    if approved_budget_acv > 0:
        if proposed_acv <= approved_budget_acv and increase_pct <= 5.0:
            negotiation_target_acv = proposed_acv
        else:
            negotiation_target_acv = approved_budget_acv
    else:
        negotiation_target_acv = round(current_acv * 1.03, 2)
        
    three_year_target = round(negotiation_target_acv * (proposed_term_months / 12.0), 2)
    budget_gap_usd = round(proposed_acv - approved_budget_acv, 2) if approved_budget_acv > 0 else 0.0

    # Seat utilization & optimization
    utilization_pct = round((active_seats / total_seats * 100), 1) if total_seats > 0 else 0.0
    
    if utilization_pct >= 90.0:
        recommended_seats = total_seats
        reduction_opportunity = 0
        seat_exposure_usd = 0.0
    else:
        # Buffer 8-10% above active seats
        recommended_seats = min(total_seats, int(round(active_seats * 1.09)))
        reduction_opportunity = max(0, total_seats - recommended_seats)
        seat_exposure_usd = round(reduction_opportunity * proposed_unit_price, 2)

    # Performance calculations
    contracted_uptime = extracted.get("contracted_uptime", 99.9)
    actual_uptime = extracted.get("actual_uptime", 99.9)
    uptime_gap = round(contracted_uptime - actual_uptime, 2)

    milestones = extracted.get("promised_milestones", [])
    roadmap_delivered_count = sum(1 for m in milestones if m.get("delivered"))
    roadmap_total_count = len(milestones)
    roadmap_delayed = [m.get("feature") for m in milestones if not m.get("delivered")]

    # Notice deadline risk check
    notice_at_risk = False
    try:
        notice_dt = datetime.strptime(extracted.get("notice_deadline", ""), "%Y-%m-%d")
        today = datetime.now()
        days_remaining = (notice_dt - today).days
        if days_remaining <= 21:  # less than 3 weeks to notice deadline
            notice_at_risk = True
    except Exception:
        notice_at_risk = True

    return {
        "increase_pct": increase_pct,
        "increase_usd": increase_usd,
        "utilization_pct": utilization_pct,
        "recommended_seats": recommended_seats,
        "reduction_opportunity": reduction_opportunity,
        "seat_exposure_usd": seat_exposure_usd,
        "three_year_baseline": three_year_baseline,
        "three_year_proposal": three_year_proposal,
        "negotiation_target_acv": negotiation_target_acv,
        "three_year_target": three_year_target,
        "budget_gap_usd": budget_gap_usd,
        "uptime_gap": uptime_gap,
        "roadmap_delivered_count": roadmap_delivered_count,
        "roadmap_total_count": roadmap_total_count,
        "roadmap_delayed": roadmap_delayed,
        "notice_at_risk": notice_at_risk
    }
