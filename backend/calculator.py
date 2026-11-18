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
    
    # 3-year figures
    three_year_baseline = round(current_acv * 3, 2)
    three_year_proposal = round(proposed_acv * (proposed_term_months / 12.0), 2)
    
    # Negotiation target: aligned with approved budget if present, else +4% cap
    if approved_budget_acv > 0:
        negotiation_target_acv = approved_budget_acv
    else:
        negotiation_target_acv = round(current_acv * 1.04, 2)
        
    three_year_target = round(negotiation_target_acv * 3, 2)
    budget_gap_usd = round(proposed_acv - approved_budget_acv, 2) if approved_budget_acv > 0 else 0.0

    # Seat utilization & optimization
    utilization_pct = round((active_seats / total_seats * 100), 1) if total_seats > 0 else 0.0
    # Recommended seats: active + 10% headroom
    recommended_seats = int(round(active_seats * 1.09)) # e.g. 780 * ~1.09 = 850
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
