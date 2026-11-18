from datetime import datetime, timedelta
from typing import Dict, Any

def extract_fields(raw: Dict[str, Any]) -> Dict[str, Any]:
    vendor = raw.get("vendor", {})
    msa = raw.get("msa", {})
    current_pricing = raw.get("current_pricing", {})
    proposal = raw.get("vendor_proposal", {})
    sla = raw.get("sla", {})
    usage = raw.get("usage", {})
    roadmap = raw.get("roadmap", {})
    emails = raw.get("emails", [])
    internal = raw.get("internal_assessment", {})
    addenda = raw.get("addendum", [])

    # Calculate notice deadline
    renewal_end_str = msa.get("current_term_end", "2027-01-31")
    notice_days = msa.get("notice_period_days", 60)
    try:
        end_dt = datetime.strptime(renewal_end_str, "%Y-%m-%d")
        notice_dt = end_dt - timedelta(days=notice_days)
        notice_deadline_str = notice_dt.strftime("%Y-%m-%d")
    except Exception:
        notice_deadline_str = "2026-12-02"

    assessment_date_str = datetime.now().strftime("%Y-%m-%d")

    # Standard renewal timeline execution plan
    timeline = {
        "total_duration": "4–6 weeks",
        "steps": [
            {
                "phase": "Financial and usage validation",
                "duration": "2–3 working days",
                "owners": ["Procurement", "Finance", "IT"],
                "description": "Validate invoices, license activity, unit pricing and future demand."
            },
            {
                "phase": "Market and alternative benchmarking",
                "duration": "3–5 working days",
                "owners": ["Procurement", "IT"],
                "description": "Identify competing vendors, comparable offerings and switching complexity."
            },
            {
                "phase": "Stakeholder and technical assessment",
                "duration": "3–5 working days",
                "owners": ["Business owners", "IT", "Security"],
                "description": "Confirm business dependency, product gaps, security requirements and roadmap priorities."
            },
            {
                "phase": "Negotiation preparation",
                "duration": "1–2 working days",
                "owners": ["Procurement", "Finance"],
                "description": "Establish target price, fallback position, negotiation levers and approval limits."
            },
            {
                "phase": "Vendor negotiation",
                "duration": "1–3 weeks",
                "owners": ["Procurement", "Vendor management"],
                "description": "Negotiate pricing, licensing, service levels and commercial protections."
            },
            {
                "phase": "Final approval and contract execution",
                "duration": "2–5 working days",
                "owners": ["Legal", "Finance", "IT leadership"],
                "description": "Validate negotiated terms, approve the final proposal and execute the renewal."
            }
        ],
        "milestones": [
            { "milestone": "Assessment initiated", "date": assessment_date_str, "critical": False },
            { "milestone": "Negotiation begins", "date": (datetime.strptime(assessment_date_str, "%Y-%m-%d") + timedelta(days=8)).strftime("%Y-%m-%d"), "critical": False },
            { "milestone": f"Notice deadline ({notice_days} days)", "date": notice_deadline_str, "critical": True },
            { "milestone": "Target decision", "date": (datetime.strptime(notice_deadline_str, "%Y-%m-%d") + timedelta(days=13)).strftime("%Y-%m-%d"), "critical": False },
            { "milestone": "Contract renewal", "date": renewal_end_str, "critical": False }
        ]
    }

    return {
        "case_id": raw.get("case_id", "UNKNOWN"),
        "assessment_date": assessment_date_str,
        "renewal_deadline": renewal_end_str,
        "notice_deadline": notice_deadline_str,
        "notice_days": notice_days,
        "auto_renewal": msa.get("auto_renewal", True),
        "termination_for_convenience": msa.get("termination_for_convenience", False),
        
        "vendor_name": vendor.get("name", "Vendor"),
        "service_type": vendor.get("service_type", "SaaS Platform"),
        "account_manager": vendor.get("account_manager", "N/A"),
        
        "current_acv": float(current_pricing.get("annual_contract_value", 0)),
        "proposed_acv": float(proposal.get("proposed_annual_value", 0)),
        "proposed_term_months": int(proposal.get("proposed_term_months", 36)),
        "current_unit_price": float(current_pricing.get("unit_price_per_seat", 0)),
        "proposed_unit_price": float(proposal.get("proposed_unit_price", 0)),
        "price_justification": proposal.get("price_increase_justification", ""),
        
        "total_seats": int(current_pricing.get("total_seats", usage.get("total_provisioned_seats", 0))),
        "active_seats": int(usage.get("active_seats_last_90_days", 0)),
        "inactive_seats": int(usage.get("inactive_seats", 0)),
        "departments": usage.get("departments", []),
        
        "contracted_uptime": float(sla.get("contracted_uptime_pct", 99.9)),
        "actual_uptime": float(sla.get("actual_uptime_pct", 99.9)),
        "support_sla_achievement": float(sla.get("actual_support_sla_achievement_pct", 100)),
        "critical_incidents_count": int(sla.get("critical_incidents_count", 0)),
        "service_credits_available": float(sla.get("service_credits_available_usd", 0)),
        "service_credits_claimed": float(sla.get("service_credits_claimed_usd", 0)),
        
        "promised_milestones": roadmap.get("promised_milestones", []),
        "addenda": addenda,
        "emails": emails,
        
        "approved_budget_acv": float(internal.get("approved_budget_acv", 0)),
        "strategic_importance": internal.get("strategic_importance", "Medium"),
        "known_alternatives": internal.get("known_alternatives", []),
        "migration_estimate_months": internal.get("migration_estimate_months", 6),
        "timeline": timeline
    }
