from typing import Dict, Any, List

def assess_performance_and_risk(extracted: Dict[str, Any], calculations: Dict[str, Any]) -> Dict[str, Any]:
    uptime_gap = calculations.get("uptime_gap", 0.0)
    support_sla = extracted.get("support_sla_achievement", 100.0)
    critical_incidents = extracted.get("critical_incidents_count", 0)
    increase_pct = calculations.get("increase_pct", 0.0)
    utilization_pct = calculations.get("utilization_pct", 100.0)
    inactive_seats = extracted.get("inactive_seats", 0)
    term_months = extracted.get("proposed_term_months", 36)
    delayed_roadmap = calculations.get("roadmap_delayed", [])
    alternatives = extracted.get("known_alternatives", [])
    service_credits = extracted.get("service_credits_available", 0.0)

    # 1. Performance rating
    if uptime_gap > 0.15 or support_sla < 75.0 or critical_incidents >= 3:
        performance_rating = "Needs Improvement"
    elif uptime_gap <= 0.05 and support_sla >= 90.0 and critical_incidents == 0:
        performance_rating = "Good"
    else:
        performance_rating = "Acceptable"

    performance_observations = []
    if critical_incidents == 0:
        performance_observations.append("Zero critical production outages recorded during the contractual term.")
    else:
        performance_observations.append(f"{critical_incidents} critical service disruptions impacted operations during the contract term.")

    if support_sla >= 90.0:
        performance_observations.append(f"Vendor consistently achieved contractual support response SLAs ({support_sla}%).")
    else:
        performance_observations.append(f"Support response SLA achievement ({support_sla}%) is below the contractual commitment.")

    if len(delayed_roadmap) > 0:
        performance_observations.append(f"{len(delayed_roadmap)} committed product roadmap features remain undelivered ({', '.join(delayed_roadmap)}).")
    else:
        performance_observations.append("All contracted feature roadmap commitments have been successfully delivered.")

    if utilization_pct >= 90.0:
        performance_observations.append(f"High seat adoption across departments ({utilization_pct}% active utilization).")
    else:
        performance_observations.append(f"Active seat utilization is at {utilization_pct}%, indicating {inactive_seats:,} inactive seats.")

    # 2. Risk Register
    risk_items: List[Dict[str, str]] = []
    high_risk_count = 0

    if increase_pct >= 25.0:
        risk_items.append({"risk": f"Severe price escalation (+{increase_pct}%)", "level": "High", "impact": "Substantial unbudgeted financial exposure"})
        high_risk_count += 1
    elif increase_pct >= 10.0:
        risk_items.append({"risk": f"Commercial price increase (+{increase_pct}%)", "level": "High" if increase_pct >= 15 else "Medium", "impact": "Budget overrun without corresponding increase in service capacity"})
        if increase_pct >= 15:
            high_risk_count += 1

    if utilization_pct < 80.0:
        risk_items.append({"risk": f"Underutilized licenses ({inactive_seats:,} inactive seats)", "level": "Medium", "impact": f"Annualized waste exposure (${calculations.get('seat_exposure_usd', 0):,.0f})"})

    if support_sla < 75.0 or critical_incidents >= 3 or uptime_gap > 0.15:
        risk_items.append({"risk": "Chronic SLA underperformance & disruption", "level": "High", "impact": "Operational downtime and productivity degradation"})
        high_risk_count += 1

    if term_months >= 36 and (increase_pct > 5.0 or performance_rating == "Needs Improvement"):
        risk_items.append({"risk": f"{term_months}-month term lock-in", "level": "Medium", "impact": "Reduced commercial and architectural flexibility"})

    if not extracted.get("termination_for_convenience", False):
        risk_items.append({"risk": "No termination for convenience clause", "level": "Medium", "impact": "Inability to exit agreement early if service degrades further"})

    if len(delayed_roadmap) >= 2:
        risk_items.append({"risk": "Roadmap delivery backlogs", "level": "Medium", "impact": "Failure to realize anticipated platform capabilities"})

    if calculations.get("notice_at_risk", False):
        risk_items.append({"risk": f"Imminent {extracted.get('notice_days', 60)}-day notice deadline", "level": "High", "impact": "Automatic renewal lock-in if formal non-renewal notice is missed"})
        high_risk_count += 1

    # If everything is good, ensure there's at least one operational risk noted or marked Low
    if not risk_items:
        risk_items.append({"risk": "Standard operational dependency", "level": "Low", "impact": "Routine vendor management and monitoring required"})

    overall_risk_level = "High" if high_risk_count >= 2 else ("Medium–High" if high_risk_count == 1 else "Low" if len(risk_items) == 1 and risk_items[0]["level"] == "Low" else "Medium")

    if overall_risk_level == "High":
        critical_concern = (
            f"The proposed +{increase_pct}% commercial increase combined with operational SLA breaches "
            f"and contract notice deadlines creates severe budget and operational exposure if accepted as-is."
        )
    elif overall_risk_level == "Low":
        critical_concern = "No acute commercial or operational red flags detected. Maintain regular quarterly governance and track feature adoption."
    else:
        critical_concern = (
            f"Committing to a {term_months // 12}-year term at a +{increase_pct}% premium locks in elevated expenditure "
            f"while {100 - utilization_pct:.0f}% license shelfware and performance gaps remain unresolved."
        )

    # 3. SLA and Addendum Flags
    sla_addendum_flags = []
    for add in extracted.get("addenda", []):
        if add.get("status") == "expired":
            sla_addendum_flags.append({
                "type": "Expired Addendum Exposure",
                "detail": f"{add.get('addendum_id')}: {add.get('description')} is expired. Verify no retroactive billing."
            })
        elif add.get("status") == "active":
            sla_addendum_flags.append({
                "type": "Active Addendum Governance",
                "detail": f"{add.get('addendum_id')}: {add.get('description')} must be carried over into renewed agreement."
            })

    if service_credits > 0:
        sla_addendum_flags.append({
            "type": "Unclaimed Service Credits",
            "detail": f"${service_credits:,.0f} in eligible SLA service credits currently unapplied — prime immediate leverage for ACV reduction."
        })

    # 4. Further analysis items
    competitor_str = f"vs {', '.join(alternatives)}" if alternatives else "against market standards"
    further_analysis = [
        { "investigation": "Detailed TCO Analysis", "deliverable": f"{term_months // 12}-year financial model & scenario comparison", "time": "2–3 days" },
        { "investigation": "License Utilization Audit", "deliverable": "Department-level usage audit & reclamation plan", "time": "2 days" },
        { "investigation": "Competitor Benchmarking", "deliverable": f"Market pricing intel & feature matrix {competitor_str}", "time": "3–5 days" },
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
