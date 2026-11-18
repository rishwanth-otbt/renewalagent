"""
Move M10: Model Costs & Recommend Next Steps (Verb: Model & Recommend)
Synthesizes findings from M01-M05, models 3-year commercial exposure, scores risks, and issues the strategic verdict.
"""
from typing import Any, Dict, List
try:
    from backend.app.core.base_move import BaseMove, MoveTrace
except ImportError:
    from app.core.base_move import BaseMove, MoveTrace


class MoveM10ModelCostsAndRecommend(BaseMove):
    move_id = "M10"
    name = "Model Costs & Recommend"
    verb = "RECOMMEND"

    def run(self, dossier: Any) -> MoveTrace:
        raw = dossier.raw_data
        history = raw.get("renewal_history", [])

        # ----------------------------------------------------
        # Action A1: Model Commercial Deltas & 3-Year Exposure
        # ----------------------------------------------------
        def action_a1():
            dossier.increase_usd = round(dossier.proposed_acv - dossier.current_acv, 2)
            dossier.increase_pct = round((dossier.increase_usd / dossier.current_acv * 100), 1) if dossier.current_acv > 0 else 0.0
            
            term_factor = dossier.proposed_term_months / 12.0
            dossier.three_year_baseline = round(dossier.current_acv * term_factor, 2)
            dossier.three_year_proposal = round(dossier.proposed_acv * term_factor, 2)

            if dossier.approved_budget_acv > 0:
                if dossier.proposed_acv <= dossier.approved_budget_acv and dossier.increase_pct <= 5.0:
                    dossier.negotiation_target_acv = dossier.proposed_acv
                else:
                    dossier.negotiation_target_acv = dossier.approved_budget_acv
            else:
                dossier.negotiation_target_acv = round(dossier.current_acv * 1.03, 2)

            dossier.three_year_target = round(dossier.negotiation_target_acv * term_factor, 2)
            dossier.budget_gap_usd = round(dossier.proposed_acv - dossier.approved_budget_acv, 2) if dossier.approved_budget_acv > 0 else 0.0
            
            return f"Increase: +{dossier.increase_pct}% (+${dossier.increase_usd:,.0f}), Target ACV: ${dossier.negotiation_target_acv:,.0f}"

        self.execute_action("A1", "ModelCommercialExposure", action_a1)

        # ----------------------------------------------------
        # Action A2: Benchmark Against Historical Trends
        # ----------------------------------------------------
        def action_a2():
            total_spend = 0.0
            sum_increases = 0.0
            prev_cycles = []
            for item in history:
                inc_pct = float(item.get("increase_pct", 0.0))
                spend = float(item.get("renewed_acv", 0.0)) * (int(item.get("term_months", 12)) / 12.0)
                total_spend += spend
                sum_increases += inc_pct
                prev_cycles.append({
                    "cycle": item.get("renewal_cycle", "N/A"),
                    "seats": item.get("seats", 0),
                    "renewed_acv": float(item.get("renewed_acv", 0.0)),
                    "increase_pct": inc_pct,
                    "outcome": item.get("outcome", "")
                })

            dossier.historical_spend_to_date = round(total_spend, 2)
            dossier.historical_avg_increase_pct = round(sum_increases / len(history), 1) if history else 0.0
            dossier.current_vs_avg_increase_pct = round(dossier.increase_pct - dossier.historical_avg_increase_pct, 1)
            dossier.previous_cycles = prev_cycles
            return f"Past spend: ${dossier.historical_spend_to_date:,.0f}, Avg increase: {dossier.historical_avg_increase_pct}% (Current ask is {dossier.current_vs_avg_increase_pct}% vs avg)"

        self.execute_action("A2", "BenchmarkHistoricalTrends", action_a2)

        # ----------------------------------------------------
        # Action A3: Synthesize Consolidated Risk Register
        # ----------------------------------------------------
        def action_a3():
            risks: List[Dict[str, str]] = []
            high_count = 0

            if dossier.increase_pct >= 25.0:
                risks.append({"risk": f"Severe price escalation (+{dossier.increase_pct}%)", "level": "High", "impact": "Substantial unbudgeted financial exposure"})
                high_count += 1
            elif dossier.increase_pct >= 10.0:
                level = "High" if dossier.increase_pct >= 15 else "Medium"
                risks.append({"risk": f"Commercial price increase (+{dossier.increase_pct}%)", "level": level, "impact": "Budget overrun without enhanced capacity"})
                if level == "High":
                    high_count += 1

            if dossier.has_shelfware:
                risks.append({"risk": f"Underutilized licenses ({dossier.inactive_seats:,} inactive seats)", "level": "Medium", "impact": f"Annualized waste exposure (${dossier.annualized_waste_usd:,.0f})"})

            if dossier.support_sla_achievement < 75.0 or dossier.critical_incidents_count >= 3 or dossier.uptime_gap > 0.15:
                risks.append({"risk": "Chronic SLA underperformance & disruption", "level": "High", "impact": "Operational downtime and productivity degradation"})
                high_count += 1

            if dossier.proposed_term_months >= 36 and (dossier.increase_pct > 5.0 or dossier.performance_rating == "Needs Improvement"):
                risks.append({"risk": f"{dossier.proposed_term_months}-month term lock-in", "level": "Medium", "impact": "Reduced operational and architectural flexibility"})

            if not dossier.termination_for_convenience:
                risks.append({"risk": "No termination for convenience clause", "level": "Medium", "impact": "Inability to exit agreement early if service degrades"})

            if len(dossier.roadmap_delayed_features) >= 2:
                risks.append({"risk": "Roadmap delivery backlogs", "level": "Medium", "impact": "Failure to realize anticipated platform capabilities"})

            if dossier.notice_at_risk:
                risks.append({"risk": f"Imminent {dossier.notice_period_days}-day notice deadline", "level": "High", "impact": "Automatic renewal lock-in if formal non-renewal notice is missed"})
                high_count += 1

            if not risks:
                risks.append({"risk": "Standard operational dependency", "level": "Low", "impact": "Routine vendor management and monitoring required"})

            dossier.risk_items = risks
            dossier.risk_level = "High" if high_count >= 2 else ("Medium–High" if high_count == 1 else "Low" if len(risks) == 1 and risks[0]["level"] == "Low" else "Medium")
            
            if dossier.risk_level == "High":
                dossier.critical_concern = f"The proposed +{dossier.increase_pct}% increase combined with operational SLA breaches and impending notice cutoffs creates acute exposure if accepted as-is."
            elif dossier.risk_level == "Low":
                dossier.critical_concern = "No acute commercial or operational red flags detected. Maintain regular quarterly governance."
            else:
                dossier.critical_concern = f"Committing to a {dossier.proposed_term_months // 12}-year term at a +{dossier.increase_pct}% premium locks in elevated expenditure while shelfware and service gaps remain unresolved."

            return f"Overall Risk Level: {dossier.risk_level} ({len(risks)} risk items logged)"

        self.execute_action("A3", "SynthesizeRiskRegister", action_a3)

        # ----------------------------------------------------
        # Gate G1: Primary Strategic Recommendation Gate
        # ----------------------------------------------------
        is_switch_candidate = (dossier.increase_pct >= 30.0) or (dossier.uptime_gap > 0.5 and dossier.performance_rating == "Needs Improvement" and dossier.increase_pct >= 20.0)
        is_renew_candidate = (dossier.increase_pct <= 5.0 and dossier.performance_rating == "Good" and dossier.budget_gap_usd <= 0)

        if is_switch_candidate:
            routing_decision = "ROUTE_SWITCH_BENCHMARK"
        elif is_renew_candidate:
            routing_decision = "ROUTE_RENEW"
        else:
            routing_decision = "ROUTE_RENEGOTIATE"

        self.record_gate(
            "G1",
            "StrategicDecisionRoutingGate",
            passed=True,
            decision=routing_decision,
            details=f"Increase: +{dossier.increase_pct}%, Rating: {dossier.performance_rating}, Budget Gap: ${dossier.budget_gap_usd:,.0f}"
        )

        # ----------------------------------------------------
        # Action A4: Build "Renew" Strategic Package
        # ----------------------------------------------------
        if routing_decision == "ROUTE_RENEW":
            def action_a4():
                dossier.primary_decision = "Renew"
                dossier.decision_rationale = (
                    f"Vendor continues to demonstrate strong operational excellence with high SLA achievement ({dossier.actual_uptime}% uptime). "
                    f"The proposed price adjustment of +{dossier.increase_pct}% is modest, falls within approved budget, "
                    "and locking in the proposed term provides commercial stability."
                )
                dossier.strategic_options = [
                    {"option": "Renew as-is", "assessment": "Preferred (commercially fair and operationally stable)"},
                    {"option": "Renegotiate", "assessment": "Optional (explore minor volume rebate or multi-year prepay discount)"},
                    {"option": "Restructure licenses", "assessment": "Not required (adoption remains above 90% threshold)"},
                    {"option": "Benchmark alternatives", "assessment": "Low priority (switching costs outweigh any marginal savings)"},
                    {"option": "Switch vendor", "assessment": "Not recommended (high disruption risk for an already well-performing vendor)"}
                ]
                dossier.negotiation_objectives = [
                    f"Execute renewal at proposed ${dossier.proposed_acv:,.0f} ACV, locking in multi-year price protection.",
                    "Verify that all current security, compliance, and support addenda automatically carry over.",
                    "Include standard SLA protection guaranteeing >= 99.9% availability with financial remedies.",
                    "Secure an annual true-up mechanism allowing license expansion at the same locked-in unit price."
                ]
                dossier.fallback_strategy = "If vendor attempts last-minute commercial alterations, negotiate a 1-year bridge extension at the current rate."
                return "Configured RENEW strategic package"
            self.execute_action("A4", "BuildRenewStrategyPackage", action_a4)
        else:
            self.skip_action("A4", "BuildRenewStrategyPackage", f"Commercial terms or SLA metrics do not meet clean RENEW threshold (routed {routing_decision}).")

        # ----------------------------------------------------
        # Action A5: Build "Renegotiate" Strategic Package
        # ----------------------------------------------------
        if routing_decision == "ROUTE_RENEGOTIATE":
            def action_a5():
                dossier.primary_decision = "Renegotiate"
                dossier.decision_rationale = (
                    f"Vendor remains functionally core, but proposed +{dossier.increase_pct}% increase exceeds performance delivery. "
                    f"Underutilization ({dossier.reduction_opportunity:,} inactive seats) and SLA gaps "
                    "provide strong commercial leverage to counter-offer."
                )
                dossier.strategic_options = [
                    {"option": "Renew as-is", "assessment": f"Not recommended (creates ${dossier.budget_gap_usd:,.0f} budget gap & locks in shelfware)"},
                    {"option": "Renegotiate", "assessment": f"Preferred (counter-target ${dossier.negotiation_target_acv:,.0f} ACV with restructured seats)"},
                    {"option": "Restructure licenses", "assessment": f"Recommended (right-size from {dossier.total_provisioned_seats:,} to {dossier.recommended_seats:,} seats)"},
                    {"option": "Benchmark alternatives", "assessment": "Recommended (parallel evaluation to maintain negotiation leverage)"},
                    {"option": "Switch vendor immediately", "assessment": "Not yet justified (migration overhead exceeds current savings potential)"}
                ]
                
                credit_str = f"${dossier.service_credits_available:,.0f}" if dossier.service_credits_available > 0 else "contractual remedies"
                dossier.negotiation_objectives = [
                    f"Right-size license commitment to {dossier.recommended_seats:,} seats (releasing ~{dossier.reduction_opportunity:,} inactive licenses).",
                    f"Reject the {dossier.increase_pct}% escalation and establish counter-target at ${dossier.negotiation_target_acv:,.0f} ACV.",
                    f"Apply eligible SLA outage penalty credits ({credit_str}) against Year 1 invoicing.",
                    "Institute enforceable service credit thresholds for future availability drops below contracted target.",
                    "Introduce contract flexibility clause permitting annual ±10% seat volume adjustments.",
                    "Secure price-protection cap (maximum 3% annual escalation) for future renewal cycles."
                ]
                dossier.fallback_strategy = "If vendor rejects commercial restructuring and maintains the price hike, issue conditional notice of non-renewal prior to the cutoff while fast-tracking an RFP with short-listed alternatives."
                return "Configured RENEGOTIATE strategic package"
            self.execute_action("A5", "BuildRenegotiateStrategyPackage", action_a5)
        else:
            self.skip_action("A5", "BuildRenegotiateStrategyPackage", f"Proposal routed to alternative decision ({routing_decision}).")

        # ----------------------------------------------------
        # Action A6: Build "Switch / Benchmark" Strategic Package
        # ----------------------------------------------------
        if routing_decision == "ROUTE_SWITCH_BENCHMARK":
            def action_a6():
                dossier.primary_decision = "Switch / Benchmark"
                dossier.decision_rationale = (
                    f"The vendor's +{dossier.increase_pct}% price increase is commercially unviable and creates a substantial "
                    f"${dossier.budget_gap_usd:,.0f} budget overrun. Combined with chronic SLA underperformance, an immediate "
                    "competitive RFP and notice of non-renewal is strongly warranted."
                )
                dossier.strategic_options = [
                    {"option": "Renew as-is", "assessment": "Strongly Rejected (causes unacceptable budget deficit & condones poor SLA)"},
                    {"option": "Renegotiate", "assessment": "Last Resort (only if vendor concedes to baseline pricing and strict SLA penalties)"},
                    {"option": "Restructure licenses", "assessment": "Required if staying (reclaim unused seats immediately)"},
                    {"option": "Benchmark alternatives", "assessment": "Mandatory (launch competitive market tender with short-listed alternatives)"},
                    {"option": "Switch vendor immediately", "assessment": "Preferred / High Priority (initiate formal migration evaluation)"}
                ]
                dossier.negotiation_objectives = [
                    "Issue formal conditional Notice of Non-Renewal prior to contractual notice deadline to preserve exit rights.",
                    f"Issue aggressive counter-target of ${dossier.negotiation_target_acv:,.0f} ACV (rejecting the {dossier.increase_pct}% price hike completely).",
                    f"If staying, cut license volume to {dossier.recommended_seats:,} seats (shedding {dossier.reduction_opportunity:,} unused seats).",
                    "Incorporate a 6-month transition assistance SLA clause ensuring zero data-export or exit penalties.",
                    "Parallel-track technical discovery with alternative platforms to demonstrate viable walk-away posture."
                ]
                dossier.fallback_strategy = "If vendor refuses to roll back price increases to baseline and restore SLA commitments, execute migration plan to alternative vendor upon current contract expiration."
                return "Configured SWITCH / BENCHMARK strategic package"
            self.execute_action("A6", "BuildSwitchStrategyPackage", action_a6)
        else:
            self.skip_action("A6", "BuildSwitchStrategyPackage", f"Proposal routed to alternative decision ({routing_decision}).")

        # ----------------------------------------------------
        # Action A7: Assemble Final Executive Brief
        # ----------------------------------------------------
        def action_a7():
            dossier.brief = {
                "meta": {
                    "case_id": dossier.case_id,
                    "assessment_date": raw.get("assessment_date", "2026-11-18"),
                    "renewal_deadline": dossier.renewal_deadline,
                    "notice_deadline": dossier.notice_deadline,
                    "notice_days": dossier.notice_period_days,
                    "current_term_months": dossier.current_term_months,
                    "notice_at_risk": dossier.notice_at_risk,
                    "decision": dossier.primary_decision,
                    "confidentiality": "CONFIDENTIAL · EXECUTIVE BRIEF"
                },
                "vendor": {
                    "name": dossier.vendor_name,
                    "service": dossier.service_type,
                    "proposed_term_months": dossier.proposed_term_months,
                    "account_manager": raw.get("vendor", {}).get("account_manager", "N/A")
                },
                "financials": {
                    "current_acv": dossier.current_acv,
                    "proposed_acv": dossier.proposed_acv,
                    "increase_pct": dossier.increase_pct,
                    "increase_usd": dossier.increase_usd,
                    "negotiation_target_acv": dossier.negotiation_target_acv,
                    "three_year_baseline": dossier.three_year_baseline,
                    "three_year_proposal": dossier.three_year_proposal,
                    "three_year_target": dossier.three_year_target,
                    "approved_budget_acv": dossier.approved_budget_acv,
                    "budget_gap_usd": dossier.budget_gap_usd
                },
                "seats": {
                    "total": dossier.total_provisioned_seats,
                    "active": dossier.active_seats,
                    "inactive": dossier.inactive_seats,
                    "utilization_pct": dossier.utilization_pct,
                    "recommended_seats": dossier.recommended_seats,
                    "reduction_opportunity": dossier.reduction_opportunity,
                    "annualized_exposure_usd": dossier.annualized_waste_usd,
                    "current_unit_price": dossier.current_unit_price,
                    "proposed_unit_price": dossier.proposed_unit_price
                },
                "history_trend": {
                    "previous_increases": dossier.previous_cycles,
                    "avg_historical_increase_pct": dossier.historical_avg_increase_pct,
                    "total_spend_to_date": dossier.historical_spend_to_date,
                    "current_increase_vs_avg": dossier.current_vs_avg_increase_pct
                },
                "performance": {
                    "overall_rating": dossier.performance_rating,
                    "uptime_contracted": dossier.contracted_uptime,
                    "uptime_actual": dossier.actual_uptime,
                    "uptime_gap_pct": dossier.uptime_gap,
                    "support_sla_pct": dossier.support_sla_achievement,
                    "critical_incidents": dossier.critical_incidents_count,
                    "service_credits_unclaimed_usd": dossier.service_credits_available,
                    "roadmap_delivered": dossier.roadmap_delivered_count,
                    "roadmap_total": dossier.roadmap_total_count,
                    "roadmap_delayed": dossier.roadmap_delayed_features,
                    "key_observations": dossier.performance_observations
                },
                "risks": {
                    "overall_level": dossier.risk_level,
                    "items": dossier.risk_items,
                    "critical_concern": dossier.critical_concern
                },
                "recommendation": {
                    "primary": dossier.primary_decision,
                    "rationale": dossier.decision_rationale,
                    "options": dossier.strategic_options,
                    "negotiation_objectives": dossier.negotiation_objectives,
                    "fallback": dossier.fallback_strategy
                },
                "timeline": {
                    "total_duration": "4–6 weeks",
                    "steps": [
                        {"phase": "Financial and usage validation", "duration": "2–3 working days", "owners": ["Procurement", "Finance", "IT"], "description": "Validate invoices, license activity, unit pricing and future demand."},
                        {"phase": "Market and alternative benchmarking", "duration": "3–5 working days", "owners": ["Procurement", "IT"], "description": f"Identify competing vendors ({', '.join(dossier.known_alternatives) or 'market standard'}) and switching complexity."},
                        {"phase": "Stakeholder and technical assessment", "duration": "3–5 working days", "owners": ["Business owners", "IT", "Security"], "description": "Confirm business dependency, product gaps, security requirements and roadmap priorities."},
                        {"phase": "Negotiation preparation", "duration": "1–2 working days", "owners": ["Procurement", "Finance"], "description": "Establish target price, fallback position, negotiation levers and approval limits."},
                        {"phase": "Vendor negotiation", "duration": "1–3 weeks", "owners": ["Procurement", "Vendor management"], "description": "Negotiate pricing, licensing, service levels and commercial protections."},
                        {"phase": "Final approval and contract execution", "duration": "2–5 working days", "owners": ["Legal", "Finance", "IT leadership"], "description": "Validate negotiated terms, approve the final proposal and execute the renewal."}
                    ],
                    "milestones": [
                        {"milestone": "Assessment initiated", "date": raw.get("assessment_date", "2026-11-18"), "critical": False},
                        {"milestone": "Negotiation begins", "date": "2026-11-25", "critical": False},
                        {"milestone": f"Notice deadline ({dossier.notice_period_days} days)", "date": dossier.notice_deadline, "critical": True},
                        {"milestone": "Target decision", "date": "2026-12-15", "critical": False},
                        {"milestone": "Contract renewal", "date": dossier.renewal_deadline, "critical": False}
                    ]
                },
                "sla_addendum_flags": dossier.addenda_flags
            }
            return f"Assembled executive brief with {len(dossier.brief)} sections"

        self.execute_action("A7", "AssembleFinalDecisionBrief", action_a7)

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=f"Synthesized decision: {dossier.primary_decision} (Risk: {dossier.risk_level}, Target: ${dossier.negotiation_target_acv:,.0f})."
        )
