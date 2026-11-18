from typing import Dict, Any, List

def compare_history(raw: Dict[str, Any]) -> Dict[str, Any]:
    history: List[Dict[str, Any]] = raw.get("renewal_history", [])
    proposal = raw.get("vendor_proposal", {})
    current_pricing = raw.get("current_pricing", {})

    current_acv = float(current_pricing.get("annual_contract_value", 0))
    proposed_acv = float(proposal.get("proposed_annual_value", 0))
    current_increase_pct = 0.0
    if current_acv > 0:
        current_increase_pct = round(((proposed_acv - current_acv) / current_acv) * 100, 1)

    previous_increases = []
    total_spend = 0.0
    sum_increases = 0.0

    for item in history:
        cycle = item.get("renewal_cycle", "N/A")
        inc_pct = float(item.get("increase_pct", 0.0))
        seats = item.get("seats", 0)
        outcome = item.get("outcome", "")
        renewed_acv = float(item.get("renewed_acv", 0.0))
        term_months = int(item.get("term_months", 12))
        
        # calculate spend in this cycle
        spend = renewed_acv * (term_months / 12.0)
        total_spend += spend
        sum_increases += inc_pct
        
        previous_increases.append({
            "cycle": cycle,
            "increase_pct": inc_pct,
            "seats": seats,
            "renewed_acv": renewed_acv,
            "outcome": outcome
        })

    avg_historical_increase_pct = round(sum_increases / len(history), 1) if history else 0.0
    current_vs_avg_pct = round(current_increase_pct - avg_historical_increase_pct, 1)

    return {
        "previous_increases": previous_increases,
        "avg_historical_increase_pct": avg_historical_increase_pct,
        "total_spend_to_date": round(total_spend, 2),
        "current_increase_pct": current_increase_pct,
        "current_vs_avg_pct": current_vs_avg_pct,
        "cycles_count": len(history)
    }
