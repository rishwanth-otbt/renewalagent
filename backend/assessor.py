from typing import Dict, Any, List

def assess_performance_and_risk(extracted: Dict[str, Any], calculations: Dict[str, Any]) -> Dict[str, Any]:
    uptime_gap = calculations.get("uptime_gap", 0.0)
    support_sla = extracted.get("support_sla_achievement", 100.0)
    critical_incidents = extracted.get("critical_incidents_count", 0)
    increase_pct = calculations.get("increase_pct", 0.0)
    utilization_pct = calculations.get("utilization_pct", 100.0)
    term_months = extracted.get("proposed_term_months", 36)
    delayed_roadmap = calculations.get("roadmap_delayed", [])

    # 1. Performance rating
    if uptime_gap > 0.15 or support_sla < 75.0 or critical_incidents >= 3:
        performance_rating = "Needs Improvement"
    elif uptime_gap <= 0.05 and support_sla >= 90.0 and critical_incidents <= 1:
        performance_rating = "Good"
    else:
        performance_rating = "Acceptable"

    performance_observations = []
    if critical_incidents > 0:
        performance_observations.append(f"{critical_incidents} critical service disruptions impacted operations during the contract term.")
    if support_sla < 85.0:
        performance_observations.append(f"Support response SLA achievement ({support_sla}%) is substantially below industry standard.")
    if len(delayed_roadmap) > 0:
        performance_observations.append(f"{len(delayed_roadmap)} committed product roadmap features remain undelivered ({', '.join(delayed_roadmap)}).")
    if utilization_pct < 85.0:
        performance_observations.append(f"Active seat utilization is at {utilization_pct}%, indicating unnecessary license overhead.")

    # 2. Risk Register
    risk_items: List[Dict[str, str]] = []
    high_risk_count = 0

    if increase_pct >= 15.0:
        risk_items.append({"risk": f"{increase_pct}% price increase", "level": "High", "impact": "Budget overrun and commercial escalation"})
        high_risk_count += 1
    elif increase_pct > 7.0:
        risk_items.append({"risk": f"{increase_pct}% price increase", "level": "Medium", "impact": "Higher cost baseline without enhanced SLA"})

    if utilization_pct < 80.0:
        risk_items.append({"risk": "Underutilized licenses (220 inactive seats)", "level": "Medium", "impact": "Annualized license cost waste ($180k+ exposure)"})

    if support_sla < 75.0 or critical_incidents >= 3:
        risk_items.append({"risk": "SLA underperformance & outage frequency", "level": "High", "impact": "Unplanned business downtime and productivity loss"})
        high_risk_count += 1

    if term_months >= 36:
        risk_items.append({"risk": "Three-year long-term commitment", "level": "Medium", "impact": "Lock-in to unproven pricing tier with reduced operational agility"})

    if not extracted.get("termination_for_convenience", False):
        risk_items.append({"risk": "No termination for convenience", "level": "Medium", "impact": "Difficulty exiting contract if service quality deteriorates further"})

    if len(delayed_roadmap) >= 2:
        risk_items.append({"risk": "Vendor product roadmap delays", "level": "Medium", "impact": "Reduced enterprise value realization from delayed feature rollouts"})

    if calculations.get("notice_at_risk", False):
        risk_items.append({"risk": "Imminent non-renewal notice deadline", "level": "High", "impact": "Inadvertent auto-renewal lock-in if formal notice is not managed"})
        high_risk_count += 1

    overall_risk_level = "High" if high_risk_count >= 2 else ("Medium–High" if high_risk_count == 1 else "Medium")

    critical_concern = (
        "Committing to a 3-year agreement at a 20% premium locks the organization into elevated expenditure "
        "while active SLA failures, roadmap backlogs, and 22% license shelfware remain unaddressed."
    )

    # 3. SLA and Addendum Flags
    sla_addendum_flags = []
    for add in extracted.get("addenda", []):
        if add.get("status") == "expired":
            sla_addendum_flags.append({
                "type": "Expired Addendum Exposure",
                "detail": f"{add.get('addendum_id')}: {add.get('description')} is expired. Vendor may attempt re-pricing."
            })
        elif add.get("status") == "active":
            sla_addendum_flags.append({
                "type": "Active Addendum Governance",
                "detail": f"{add.get('addendum_id')}: {add.get('description')} must be carried over into renewed MSA."
            })

    service_credits = extracted.get("service_credits_available", 0.0)
    if service_credits > 0:
        sla_addendum_flags.append({
            "type": "Unclaimed Service Credits",
            "detail": f"${service_credits:,.0f} in eligible SLA service credits currently unapplied — prime immediate leverage for ACV reduction."
        })

    # 4. Further analysis items
    further_analysis = [
        { "investigation": "Detailed TCO Analysis", "deliverable": "3-year financial model & scenario comparison", "time": "2–3 days" },
        { "investigation": "License Utilization Deep Dive", "deliverable": "User-level usage audit & reclamation plan", "time": "2 days" },
        { "investigation": "Competitor Benchmarking", "deliverable": "Market pricing intel & feature matrix vs Salesforce/HubSpot", "time": "3–5 days" },
        { "investigation": "Technical Dependency Analysis", "deliverable": "Integration architecture & migration complexity assessment", "time": "5–7 days" },
        { "investigation": "Vendor Performance Audit", "deliverable": "Contractual SLA penalty & incident root cause log", "time": "2–3 days" },
        { "investigation": "Negotiation Playbook", "deliverable": "Walk-away thresholds & commercial counter-proposals", "time": "1–2 days" }
    ]

    return {
        "performance_rating": performance_rating,
        "performance_observations": performance_observations,
        "risk_level": overall_risk_level,
        "risk_items": risk_items,
        "critical_concern": critical_concern,
        "sla_addendum_flags": sla_addendum_flags,
        "further_analysis": further_analysis
    }
