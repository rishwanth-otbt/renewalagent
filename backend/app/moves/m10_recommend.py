"""
Move M10: Model Costs & Recommend Next Steps (Verb: Model & Recommend)
Synthesizes findings from M01-M05, models 3-year commercial exposure, scores risks, and issues the strategic verdict.

Every sentence in the recommendation is built from the facts that triggered it (decision_drivers),
so two cases routed to the same decision for different reasons get different rationales.
"""
from typing import Any, Dict, List
try:
    from backend.app.core.base_move import BaseMove, MoveTrace
except ImportError:
    from app.core.base_move import BaseMove, MoveTrace


RATING_ORDER = {"Needs Improvement": 0, "Acceptable": 1, "Good": 2}


def _fmt_usd(v: float) -> str:
    return f"${v:,.0f}"


def _rating_meets(rating: str, minimum: str) -> bool:
    return RATING_ORDER.get(rating, -1) >= RATING_ORDER[minimum]


def _check(rule_id: str, group: str, rule: str, limit: str, actual: str, passed: bool) -> Dict[str, Any]:
    """One policy rule evaluated for this case. passed=True means the rule does not stand in the way of renewing."""
    return {"id": rule_id, "group": group, "rule": rule, "limit": limit, "actual": actual, "passed": bool(passed)}


def build_rule_checks(d: Any) -> List[Dict[str, Any]]:
    """The policy rules that decide the label (M10 G1/G2), with the case's actual values."""
    rn, sw = d.policy.renew, d.policy.switch
    budget_ok = d.budget_gap_usd <= 0
    if d.approved_budget_acv <= 0:
        budget_actual = "no approved budget"
    elif budget_ok:
        budget_actual = f"{_fmt_usd(-d.budget_gap_usd)} under budget"
    else:
        budget_actual = f"{_fmt_usd(d.budget_gap_usd)} over budget"
    cap_actual = ("no cap in MSA" if d.price_cap_pct is None
                  else f"+{d.increase_pct}% vs {d.price_cap_pct:g}% cap")
    poor_perf_switch = (d.uptime_gap > sw.poor_performance_uptime_gap and d.performance_rating == "Needs Improvement"
                        and d.increase_pct >= sw.poor_performance_min_increase_pct)
    return [
        _check("renew.max_increase_pct", "Renew", "Price increase within renew limit",
               f"≤ {rn.max_increase_pct:g}%", f"+{d.increase_pct}%", d.increase_pct <= rn.max_increase_pct),
        _check("renew.min_performance_rating", "Renew", "Supplier performance rating",
               f"{rn.min_performance_rating} or better", d.performance_rating,
               _rating_meets(d.performance_rating, rn.min_performance_rating)),
        _check("renew.require_within_budget", "Renew", "Within approved budget",
               "≤ approved budget" if rn.require_within_budget else "not required", budget_actual,
               budget_ok or not rn.require_within_budget),
        _check("renew.require_within_price_cap", "Renew", "Within contractual price cap",
               "≤ contract cap" if rn.require_within_price_cap else "not required", cap_actual,
               not d.cap_breach or not rn.require_within_price_cap),
        _check("switch.price_shock_pct", "Switch", "Price increase below switch trigger",
               f"< {sw.price_shock_pct:g}%", f"+{d.increase_pct}%", d.increase_pct < sw.price_shock_pct),
        _check("switch.poor_performance", "Switch", "No poor-performance switch trigger",
               f"not (uptime gap > {sw.poor_performance_uptime_gap:g} pts, Needs Improvement, increase ≥ {sw.poor_performance_min_increase_pct:g}%)",
               f"gap {d.uptime_gap} pts, {d.performance_rating}, +{d.increase_pct}%", not poor_perf_switch),
    ]


class MoveM10ModelCostsAndRecommend(BaseMove):
    move_id = "M10"
    name = "Model Costs & Recommend"
    verb = "RECOMMEND"

    # ----------------------------------------------------
    # Notice-aware wording (depends on M03 G2 outcome)
    # ----------------------------------------------------
    @staticmethod
    def _notice_objective(d: Any) -> str:
        if d.notice_passed and d.auto_renewal:
            exit_right = ("invoke the termination-for-convenience clause if terms are not met"
                          if d.termination_for_convenience
                          else f"negotiate a mutual early-exit or a {d.policy.negotiation.bridge_term_months}-month bridge term (no termination-for-convenience right)")
            return (f"Notice deadline ({d.notice_deadline}) was missed and the contract auto-renews at term end "
                    f"({d.renewal_deadline}). Use the pending renewal as leverage and {exit_right}.")
        if d.notice_passed:
            return (f"Notice deadline ({d.notice_deadline}) has passed and there is no auto-renewal: the contract lapses on "
                    f"{d.renewal_deadline}. Secure a short bridge extension to avoid a service gap while terms are agreed.")
        if d.notice_at_risk:
            return (f"Serve conditional Notice of Non-Renewal by {d.notice_deadline} ({d.days_to_notice} days left) "
                    "to preserve exit rights and negotiation leverage.")
        return f"Serve conditional Notice of Non-Renewal before {d.notice_deadline} if acceptable terms are not agreed."

    @staticmethod
    def _notice_fallback(d: Any, stay_action: str, exit_action: str = "fast-track an RFP with short-listed alternatives") -> str:
        if d.notice_passed and d.auto_renewal:
            if d.termination_for_convenience:
                return f"{stay_action} If the vendor will not move, accept the auto-renewal and exercise termination for convenience once a replacement is ready."
            return f"{stay_action} If the vendor will not move, the contract rolls into a new term; plan the migration to land at the end of that term."
        if d.notice_passed:
            return f"{stay_action} If no agreement is reached before {d.renewal_deadline}, sign a short bridge extension at the current rate."
        return f"{stay_action} If the vendor will not move, issue notice of non-renewal before {d.notice_deadline} and {exit_action}."

    @staticmethod
    def _decided_by(d: Any) -> str:
        """One sentence naming the policy rules that produced the label."""
        def fmt(checks):
            return "; ".join(f"{c['rule']} ({c['actual']}, needs {c['limit']})" for c in checks)
        failed = [c for c in d.rule_checks if not c["passed"]]
        if d.primary_decision == "Renew":
            return "Renew: every Renew rule in the policy is met."
        if d.primary_decision == "Switch / Benchmark":
            return "Switch / Benchmark: switch rule not met — " + fmt([c for c in failed if c["group"] == "Switch"]) + "."
        renew_failed = [c for c in failed if c["group"] == "Renew"]
        text = "Renegotiate: Renew rules not met — " + fmt(renew_failed) + "." if renew_failed else "Renegotiate."
        if d.switch_downgraded:
            text += (" A switch rule was also not met, but the vendor is hard to replace and performance is not "
                     "Needs Improvement, so Switch was downgraded to Renegotiate.")
        return text

    def run(self, dossier: Any) -> MoveTrace:
        raw = dossier.raw_data
        history = raw["renewal_history"]
        internal = raw["internal_assessment"]
        pol = dossier.policy

        # ----------------------------------------------------
        # Action A1: Model Commercial Deltas & 3-Year Exposure (incl. contractual price cap)
        # ----------------------------------------------------
        def action_a1():
            dossier.increase_usd = round(dossier.proposed_acv - dossier.current_acv, 2)
            dossier.increase_pct = round((dossier.increase_usd / dossier.current_acv * 100), 1) if dossier.current_acv > 0 else 0.0

            term_factor = dossier.proposed_term_months / 12.0
            dossier.three_year_baseline = round(dossier.current_acv * term_factor, 2)
            dossier.three_year_proposal = round(dossier.proposed_acv * term_factor, 2)

            if dossier.approved_budget_acv > 0:
                if dossier.proposed_acv <= dossier.approved_budget_acv and dossier.increase_pct <= pol.renew.max_increase_pct:
                    dossier.negotiation_target_acv = dossier.proposed_acv
                else:
                    dossier.negotiation_target_acv = dossier.approved_budget_acv
            else:
                dossier.negotiation_target_acv = round(dossier.current_acv * (1 + pol.budget.no_budget_target_uplift_pct / 100), 2)

            # Contractual price-increase cap (MSA). A proposal above the cap is not enforceable as-is.
            cap = raw["msa"].get("price_increase_cap_pct")
            dossier.price_cap_pct = float(cap) if cap is not None else None
            dossier.cap_breach = cap is not None and dossier.increase_pct > float(cap)
            if dossier.cap_breach:
                dossier.capped_acv = round(dossier.current_acv * (1 + float(cap) / 100), 2)
                dossier.negotiation_target_acv = min(dossier.negotiation_target_acv, dossier.capped_acv)
            else:
                dossier.capped_acv = None

            dossier.three_year_target = round(dossier.negotiation_target_acv * term_factor, 2)
            dossier.budget_gap_usd = round(dossier.proposed_acv - dossier.approved_budget_acv, 2) if dossier.approved_budget_acv > 0 else 0.0

            cap_note = f", CAP BREACH ({dossier.increase_pct}% > {dossier.price_cap_pct}% cap)" if dossier.cap_breach else ""
            return f"Increase: +{dossier.increase_pct}% (+{_fmt_usd(dossier.increase_usd)}), Target ACV: {_fmt_usd(dossier.negotiation_target_acv)}{cap_note}"

        self.execute_action("A1", "ModelCommercialExposure", action_a1)

        # ----------------------------------------------------
        # Action A2: Benchmark Against Historical Trends
        # ----------------------------------------------------
        def action_a2():
            total_spend = 0.0
            sum_increases = 0.0
            prev_cycles = []
            for item in history:
                inc_pct = float(item["increase_pct"])
                spend = float(item["renewed_acv"]) * (item["term_months"] / 12.0)
                total_spend += spend
                sum_increases += inc_pct
                prev_cycles.append({
                    "cycle": item["renewal_cycle"],
                    "seats": item["seats"],
                    "renewed_acv": float(item["renewed_acv"]),
                    "increase_pct": inc_pct,
                    "outcome": item["outcome"]
                })

            dossier.historical_spend_to_date = round(total_spend, 2)
            dossier.historical_avg_increase_pct = round(sum_increases / len(history), 1) if history else 0.0
            dossier.current_vs_avg_increase_pct = round(dossier.increase_pct - dossier.historical_avg_increase_pct, 1)
            dossier.previous_cycles = prev_cycles
            return f"Past spend: {_fmt_usd(dossier.historical_spend_to_date)}, Avg increase: {dossier.historical_avg_increase_pct}% (Current ask is {dossier.current_vs_avg_increase_pct}% vs avg)"

        self.execute_action("A2", "BenchmarkHistoricalTrends", action_a2)

        # ----------------------------------------------------
        # Action A3: Synthesize Consolidated Risk Register
        # ----------------------------------------------------
        def action_a3():
            risks: List[Dict[str, str]] = []

            if dossier.increase_pct >= pol.risk.severe_increase_pct:
                risks.append({"risk": f"Severe price escalation (+{dossier.increase_pct}%)", "level": "High", "impact": "Substantial unbudgeted financial exposure"})
            elif dossier.increase_pct >= pol.risk.medium_increase_pct:
                level = "High" if dossier.increase_pct >= pol.risk.high_increase_pct else "Medium"
                risks.append({"risk": f"Commercial price increase (+{dossier.increase_pct}%)", "level": level, "impact": "Budget overrun without enhanced capacity"})

            if dossier.cap_breach:
                risks.append({"risk": f"Proposal breaches contractual {dossier.price_cap_pct:g}% price-increase cap",
                              "level": "High",
                              "impact": f"Increase above cap is not contractually supported; capped ACV is {_fmt_usd(dossier.capped_acv)}"})

            if dossier.has_shelfware:
                risks.append({"risk": f"Underutilized licenses ({dossier.inactive_seats:,} inactive seats)", "level": "Medium", "impact": f"Annualized waste exposure ({_fmt_usd(dossier.annualized_waste_usd)})"})

            if dossier.renewal_type == "EXPANSION" and dossier.has_shelfware:
                risks.append({"risk": f"Seat expansion (+{dossier.seat_change:,}) not supported by usage", "level": "Medium", "impact": "Paying for growth while current seats sit idle"})

            if dossier.added_modules:
                risks.append({"risk": f"Bundled new modules ({', '.join(dossier.added_modules)})", "level": "Medium" if dossier.increase_pct > pol.renew.max_increase_pct else "Low",
                              "impact": "Scope added to the renewal may be driving part of the price increase"})

            # M04 already applied policy.performance; "Needs Improvement" is exactly the poor-SLA rule.
            if dossier.performance_rating == "Needs Improvement":
                risks.append({"risk": "Chronic SLA underperformance & disruption", "level": "High", "impact": "Operational downtime and productivity degradation"})

            if (dossier.proposed_term_months >= pol.risk.long_term_months
                    and (dossier.increase_pct > pol.renew.max_increase_pct or dossier.performance_rating == "Needs Improvement")):
                risks.append({"risk": f"{dossier.proposed_term_months}-month term lock-in", "level": "Medium", "impact": "Reduced operational and architectural flexibility"})

            if not dossier.termination_for_convenience:
                risks.append({"risk": "No termination for convenience clause", "level": "Medium", "impact": "Inability to exit agreement early if service degrades"})

            if len(dossier.roadmap_delayed_features) >= pol.risk.roadmap_backlog_count:
                risks.append({"risk": "Roadmap delivery backlogs", "level": "Medium", "impact": "Failure to realize anticipated platform capabilities"})

            if dossier.notice_passed and dossier.auto_renewal:
                risks.append({"risk": f"Notice deadline missed ({dossier.notice_deadline})", "level": "High",
                              "impact": "Contract auto-renews into a new term; exit now needs vendor agreement or a termination right"})
            elif dossier.notice_passed:
                risks.append({"risk": f"Notice window closed; contract lapses {dossier.renewal_deadline}", "level": "Medium",
                              "impact": "Service gap if renewal terms are not signed before term end"})
            elif dossier.notice_at_risk:
                risks.append({"risk": f"Imminent {dossier.notice_period_days}-day notice deadline ({dossier.days_to_notice} days left)", "level": "High",
                              "impact": "Automatic renewal lock-in if formal non-renewal notice is missed"})

            if not risks:
                risks.append({"risk": "Standard operational dependency", "level": "Low", "impact": "Routine vendor management and monitoring required"})

            high = [r for r in risks if r["level"] == "High"]
            dossier.risk_items = risks
            if len(high) >= pol.risk.high_items_for_high_level:
                dossier.risk_level = "High"
            elif high:
                dossier.risk_level = "Medium–High"
            elif len(risks) == 1 and risks[0]["level"] == "Low":
                dossier.risk_level = "Low"
            else:
                dossier.risk_level = "Medium"

            if dossier.risk_level == "Low":
                dossier.critical_concern = "No acute commercial or operational red flags detected. Maintain regular quarterly governance."
            else:
                top = high if high else [r for r in risks if r["level"] == "Medium"]
                dossier.critical_concern = "Accepting the proposal as-is exposes the organization to: " + "; ".join(r["risk"] for r in top[:4]) + "."

            return f"Overall Risk Level: {dossier.risk_level} ({len(risks)} risk items logged, {len(high)} high)"

        self.execute_action("A3", "SynthesizeRiskRegister", action_a3)

        # ----------------------------------------------------
        # Decision drivers: the facts that push away from a clean renewal
        # ----------------------------------------------------
        drivers: List[str] = []
        if dossier.increase_pct > pol.renew.max_increase_pct:
            drivers.append(f"+{dossier.increase_pct}% price increase (historical average {dossier.historical_avg_increase_pct}%)")
        if dossier.cap_breach:
            drivers.append(f"increase exceeds the contractual {dossier.price_cap_pct:g}% cap")
        if dossier.budget_gap_usd > 0:
            drivers.append(f"{_fmt_usd(dossier.budget_gap_usd)} over the approved budget")
        if dossier.has_shelfware:
            drivers.append(f"{dossier.utilization_pct}% seat utilization ({dossier.inactive_seats:,} inactive seats)")
        if not _rating_meets(dossier.performance_rating, pol.renew.min_performance_rating):
            drivers.append(
                f"performance rated {dossier.performance_rating} ({dossier.actual_uptime}% uptime vs {dossier.contracted_uptime}% contracted, "
                f"{dossier.support_sla_achievement}% support SLA, {dossier.critical_incidents_count} critical incidents)"
            )
        if dossier.added_modules:
            drivers.append(f"new modules bundled into the renewal ({', '.join(dossier.added_modules)})")
        if dossier.renewal_type == "EXPANSION" and dossier.has_shelfware:
            drivers.append(f"+{dossier.seat_change:,} seat expansion despite idle seats")
        dossier.decision_drivers = drivers

        # ----------------------------------------------------
        # Gate G1: Primary Strategic Recommendation Gate
        # ----------------------------------------------------
        sw, rn = pol.switch, pol.renew
        is_switch_candidate = (dossier.increase_pct >= sw.price_shock_pct) or (
            dossier.uptime_gap > sw.poor_performance_uptime_gap
            and dossier.performance_rating == "Needs Improvement"
            and dossier.increase_pct >= sw.poor_performance_min_increase_pct)
        is_renew_candidate = (dossier.increase_pct <= rn.max_increase_pct
                              and _rating_meets(dossier.performance_rating, rn.min_performance_rating)
                              and (dossier.budget_gap_usd <= 0 or not rn.require_within_budget)
                              and (not dossier.cap_breach or not rn.require_within_price_cap))

        dossier.rule_checks = build_rule_checks(dossier)

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
            details=(f"Increase: +{dossier.increase_pct}% (renew ≤ {rn.max_increase_pct:g}%, switch ≥ {sw.price_shock_pct:g}%), "
                     f"Rating: {dossier.performance_rating} (renew needs {rn.min_performance_rating}), "
                     f"Budget Gap: {_fmt_usd(dossier.budget_gap_usd)}, Cap breach: {dossier.cap_breach}")
        )

        # ----------------------------------------------------
        # Gate G2: Switching-Cost Gate
        # A switch driven by price alone is downgraded to renegotiate when the vendor is hard to replace.
        # ----------------------------------------------------
        replacement_difficulty = internal["replacement_difficulty"]
        migration_months = internal["migration_estimate_months"]
        dossier.hard_to_replace = (replacement_difficulty.strip().lower() in sw.hard_to_replace_levels
                                   or migration_months >= sw.long_migration_months)
        dossier.switch_downgraded = (routing_decision == "ROUTE_SWITCH_BENCHMARK"
                                     and dossier.hard_to_replace
                                     and dossier.performance_rating != "Needs Improvement")
        dossier.rule_checks.append(_check(
            "switch.hard_to_replace", "Switching cost", "Vendor can be replaced",
            f"difficulty not in ({', '.join(sw.hard_to_replace_levels)}) and migration < {sw.long_migration_months} months",
            f"{replacement_difficulty}, {migration_months} months", not dossier.hard_to_replace))
        if dossier.switch_downgraded:
            routing_decision = "ROUTE_RENEGOTIATE"
            g2_decision = "DOWNGRADE_TO_RENEGOTIATE"
        elif dossier.hard_to_replace:
            g2_decision = "HARD_TO_REPLACE_NOTED"
        else:
            g2_decision = "SWITCHING_FEASIBLE"
        self.record_gate(
            "G2",
            "SwitchingCostGate",
            passed=True,
            decision=g2_decision,
            details=(f"Replacement difficulty: {replacement_difficulty} (hard: {', '.join(sw.hard_to_replace_levels)}), "
                     f"migration estimate: {migration_months} months (hard from {sw.long_migration_months}), rating: {dossier.performance_rating}")
        )

        drivers_text = "; ".join(drivers)
        target_util = pol.licenses.target_utilization_pct
        notice_obj = self._notice_objective(dossier)

        # ----------------------------------------------------
        # Action A4: Build "Renew" Strategic Package
        # ----------------------------------------------------
        if routing_decision == "ROUTE_RENEW":
            def action_a4():
                dossier.primary_decision = "Renew"
                if dossier.approved_budget_acv <= 0:
                    budget_text = "no approved budget is on file"
                elif dossier.budget_gap_usd > 0:
                    budget_text = f"is {_fmt_usd(dossier.budget_gap_usd)} over budget (allowed by policy)"
                else:
                    budget_text = f"leaves {_fmt_usd(-dossier.budget_gap_usd)} of budget headroom"
                dossier.decision_rationale = (
                    f"Performance rated {dossier.performance_rating} (policy minimum: {rn.min_performance_rating}): "
                    f"{dossier.actual_uptime}% uptime vs {dossier.contracted_uptime}% contracted, "
                    f"{dossier.support_sla_achievement}% support SLA and {dossier.critical_incidents_count} critical incidents. "
                    f"The +{dossier.increase_pct}% increase is within the {rn.max_increase_pct:g}% renew limit "
                    f"(historical average {dossier.historical_avg_increase_pct}%) "
                    f"and {budget_text}, with {dossier.utilization_pct}% of seats in active use."
                )
                if dossier.price_cap_pct is not None:
                    dossier.decision_rationale += f" The increase is within the contractual {dossier.price_cap_pct:g}% cap."
                dossier.strategic_options = [
                    {"option": "Renew as-is", "assessment": "Preferred (commercially fair and operationally stable)"},
                    {"option": "Renegotiate", "assessment": "Optional (explore minor volume rebate or multi-year prepay discount)"},
                    {"option": "Restructure licenses",
                     "assessment": (f"Optional ({dossier.utilization_pct}% adoption is below the {target_util:g}% target; "
                                    f"right-size to {dossier.recommended_seats:,} seats)" if dossier.has_shelfware
                                    else f"Not required ({dossier.utilization_pct}% adoption meets the {target_util:g}% target)")},
                    {"option": "Benchmark alternatives", "assessment": f"Low priority (replacement difficulty {replacement_difficulty}, ~{migration_months}-month migration)"},
                    {"option": "Switch vendor", "assessment": "Not recommended (high disruption risk for a well-performing vendor)"}
                ]
                objectives = [
                    f"Execute renewal at proposed {_fmt_usd(dossier.proposed_acv)} ACV, locking in multi-year price protection.",
                    "Verify that all current security, compliance, and support addenda automatically carry over.",
                    f"Keep SLA protection at >= {dossier.contracted_uptime}% availability with financial remedies.",
                    "Secure an annual true-up mechanism allowing license expansion at the same locked-in unit price."
                ]
                if dossier.added_modules:
                    objectives.append(f"Get {', '.join(dossier.added_modules)} quoted as a separate optional line item, not bundled into the renewal.")
                if dossier.notice_passed and not dossier.auto_renewal:
                    objectives.insert(0, f"Sign before term end ({dossier.renewal_deadline}); there is no auto-renewal and the notice window has closed.")
                dossier.negotiation_objectives = objectives
                dossier.fallback_strategy = (f"If the vendor attempts last-minute commercial changes, negotiate a "
                                             f"{pol.negotiation.bridge_term_months}-month bridge extension at the current rate.")
                return "Configured RENEW strategic package"
            self.execute_action("A4", "BuildRenewStrategyPackage", action_a4)
        else:
            self.skip_action("A4", "BuildRenewStrategyPackage", f"Proposal does not meet the policy's Renew rules (routed {routing_decision}).")

        # ----------------------------------------------------
        # Action A5: Build "Renegotiate" Strategic Package
        # ----------------------------------------------------
        if routing_decision == "ROUTE_RENEGOTIATE":
            def action_a5():
                dossier.primary_decision = "Renegotiate"
                rationale = f"Vendor remains functionally core, but the proposal does not meet renewal criteria. Drivers: {drivers_text}."
                if dossier.switch_downgraded:
                    rationale += (f" The price increase alone would justify switching, but replacement difficulty is {replacement_difficulty} "
                                  f"(~{migration_months}-month migration) and performance is {dossier.performance_rating}, "
                                  "so a competitive benchmark is used as leverage instead of an immediate switch.")
                dossier.decision_rationale = rationale

                renew_as_is = (f"Not recommended (creates {_fmt_usd(dossier.budget_gap_usd)} budget gap)" if dossier.budget_gap_usd > 0
                               else f"Not recommended (accepts +{dossier.increase_pct}% without concessions)")
                dossier.strategic_options = [
                    {"option": "Renew as-is", "assessment": renew_as_is},
                    {"option": "Renegotiate", "assessment": f"Preferred (counter-target {_fmt_usd(dossier.negotiation_target_acv)} ACV)"},
                    {"option": "Restructure licenses",
                     "assessment": (f"Recommended (right-size from {dossier.total_provisioned_seats:,} to {dossier.recommended_seats:,} seats)"
                                    if dossier.has_shelfware else f"Not required ({dossier.utilization_pct}% adoption meets the {target_util:g}% target)")},
                    {"option": "Benchmark alternatives", "assessment": "Recommended (parallel evaluation to maintain negotiation leverage)"},
                    {"option": "Switch vendor immediately",
                     "assessment": (f"Not justified (replacement difficulty {replacement_difficulty}, ~{migration_months}-month migration)"
                                    if dossier.hard_to_replace else "Not yet justified (migration overhead exceeds current savings potential)")}
                ]

                objectives: List[str] = []
                if dossier.notice_passed or dossier.notice_at_risk:
                    objectives.append(notice_obj)
                if dossier.cap_breach:
                    objectives.append(f"Enforce the contractual {dossier.price_cap_pct:g}% price-increase cap: maximum ACV {_fmt_usd(dossier.capped_acv)} "
                                      f"(vendor asked +{dossier.increase_pct}%).")
                if dossier.increase_pct > pol.renew.max_increase_pct or dossier.budget_gap_usd > 0:
                    objectives.append(f"Reject the +{dossier.increase_pct}% escalation and counter at {_fmt_usd(dossier.negotiation_target_acv)} ACV.")
                if dossier.has_shelfware:
                    objectives.append(f"Right-size license commitment to {dossier.recommended_seats:,} seats (releasing ~{dossier.reduction_opportunity:,} inactive licenses).")
                if dossier.renewal_type == "EXPANSION" and dossier.has_shelfware:
                    objectives.append(f"Decline the proposed +{dossier.seat_change:,} seat expansion until current seats are in use.")
                if dossier.added_modules:
                    objectives.append(f"Unbundle {', '.join(dossier.added_modules)} from the renewal and price it separately, or remove it.")
                if dossier.service_credits_available > 0:
                    objectives.append(f"Apply {_fmt_usd(dossier.service_credits_available)} of unclaimed SLA service credits against Year 1 invoicing.")
                if dossier.performance_rating != "Good":
                    objectives.append(f"Institute enforceable service credits for availability below {dossier.contracted_uptime}% and support SLA misses.")
                objectives.append(f"Introduce a contract flexibility clause permitting annual ±{pol.negotiation.seat_flex_pct:g}% seat volume adjustments.")
                objectives.append(f"Secure a price-protection cap (maximum {pol.negotiation.future_price_cap_pct:g}% annual escalation) for future renewal cycles.")
                dossier.negotiation_objectives = objectives

                dossier.fallback_strategy = self._notice_fallback(
                    dossier, "Hold the counter-target and keep the benchmark running in parallel.")
                return "Configured RENEGOTIATE strategic package" + (" (downgraded from SWITCH by switching-cost gate)" if dossier.switch_downgraded else "")
            self.execute_action("A5", "BuildRenegotiateStrategyPackage", action_a5)
        else:
            self.skip_action("A5", "BuildRenegotiateStrategyPackage", f"Proposal routed to alternative decision ({routing_decision}).")

        # ----------------------------------------------------
        # Action A6: Build "Switch / Benchmark" Strategic Package
        # ----------------------------------------------------
        if routing_decision == "ROUTE_SWITCH_BENCHMARK":
            def action_a6():
                dossier.primary_decision = "Switch / Benchmark"
                rationale = f"The proposal is not commercially or operationally viable. Drivers: {drivers_text}."
                if dossier.hard_to_replace:
                    rationale += (f" Replacement difficulty is {replacement_difficulty} (~{migration_months}-month migration), "
                                  "but performance is too poor to justify staying on these terms.")
                rationale += " A competitive RFP is warranted, with the incumbent kept in the process only on reset terms."
                dossier.decision_rationale = rationale
                dossier.strategic_options = [
                    {"option": "Renew as-is", "assessment": "Strongly Rejected (unacceptable cost and/or service terms)"},
                    {"option": "Renegotiate", "assessment": "Last Resort (only if vendor concedes to baseline pricing and strict SLA penalties)"},
                    {"option": "Restructure licenses",
                     "assessment": "Required if staying (reclaim unused seats immediately)" if dossier.has_shelfware else "Not a lever (adoption is healthy)"},
                    {"option": "Benchmark alternatives", "assessment": "Mandatory (launch competitive market tender with short-listed alternatives)"},
                    {"option": "Switch vendor", "assessment": f"Preferred (initiate formal migration evaluation, ~{migration_months}-month effort)"}
                ]
                objectives = [notice_obj]
                objectives.append(f"Counter at {_fmt_usd(dossier.negotiation_target_acv)} ACV, rejecting the +{dossier.increase_pct}% increase.")
                if dossier.cap_breach:
                    objectives.append(f"Enforce the contractual {dossier.price_cap_pct:g}% cap (maximum {_fmt_usd(dossier.capped_acv)} ACV) if any extension is needed.")
                if dossier.has_shelfware:
                    objectives.append(f"If staying, cut license volume to {dossier.recommended_seats:,} seats (shedding {dossier.reduction_opportunity:,} unused seats).")
                if dossier.added_modules:
                    objectives.append(f"Refuse bundled additions ({', '.join(dossier.added_modules)}).")
                objectives.append(f"Incorporate a {pol.negotiation.transition_assistance_months}-month transition assistance clause ensuring zero data-export or exit penalties.")
                objectives.append("Parallel-track technical discovery with alternative platforms to demonstrate a viable walk-away posture.")
                dossier.negotiation_objectives = objectives
                dossier.fallback_strategy = self._notice_fallback(
                    dossier, "Run the RFP to completion and keep the incumbent only if it matches baseline pricing and restores SLA commitments.",
                    exit_action="execute the migration to the selected alternative at contract expiry")
                return "Configured SWITCH / BENCHMARK strategic package"
            self.execute_action("A6", "BuildSwitchStrategyPackage", action_a6)
        else:
            self.skip_action("A6", "BuildSwitchStrategyPackage", f"Proposal routed to alternative decision ({routing_decision}).")

        # ----------------------------------------------------
        # Action A7: Build Decision-Specific Execution Timeline
        # ----------------------------------------------------
        def action_a7():
            alternatives_text = (
                ", ".join(dossier.known_alternatives)
                if dossier.known_alternatives
                else "none listed in the internal assessment"
            )
            if dossier.primary_decision == "Renew":
                duration = "1–2 weeks"
                steps = [
                    {"phase": "Financial and usage validation", "duration": "2–3 working days", "owners": ["Procurement", "Finance", "IT"], "description": "Confirm invoice, seat count and unit price match the proposal."},
                    {"phase": "Terms carry-over check", "duration": "2–3 working days", "owners": ["Legal", "IT"], "description": "Confirm active addenda, SLA remedies and price protection carry into the new term."},
                    {"phase": "Final approval and contract execution", "duration": "2–5 working days", "owners": ["Legal", "Finance", "IT leadership"], "description": "Approve within budget authority and execute the renewal."},
                ]
            elif dossier.primary_decision == "Renegotiate":
                duration = "4–6 weeks"
                steps = [
                    {"phase": "Financial and usage validation", "duration": "2–3 working days", "owners": ["Procurement", "Finance", "IT"], "description": "Validate invoices, license activity, unit pricing and future demand."},
                    {"phase": "Market and alternative benchmarking", "duration": "3–5 working days", "owners": ["Procurement", "IT"], "description": f"Benchmark competing vendors ({alternatives_text}) to build leverage."},
                    {"phase": "Stakeholder and technical assessment", "duration": "3–5 working days", "owners": ["Business owners", "IT", "Security"], "description": "Confirm business dependency, product gaps, security requirements and roadmap priorities."},
                    {"phase": "Negotiation preparation", "duration": "1–2 working days", "owners": ["Procurement", "Finance"], "description": "Set counter-target, fallback position, levers and approval limits."},
                    {"phase": "Vendor negotiation", "duration": "1–3 weeks", "owners": ["Procurement", "Vendor management"], "description": "Negotiate pricing, licensing, service levels and commercial protections."},
                    {"phase": "Final approval and contract execution", "duration": "2–5 working days", "owners": ["Legal", "Finance", "IT leadership"], "description": "Validate negotiated terms, approve and execute."},
                ]
            else:
                duration = "8–12 weeks"
                steps = [
                    {"phase": "Requirements and RFP preparation", "duration": "1–2 weeks", "owners": ["IT", "Procurement", "Business owners"], "description": "Document requirements and short-list alternatives."},
                    {"phase": "Competitive RFP", "duration": "2–3 weeks", "owners": ["Procurement"], "description": f"Run tender with {alternatives_text}; incumbent invited on reset terms only."},
                    {"phase": "Proof of concept and migration sizing", "duration": "3–4 weeks", "owners": ["IT", "Security"], "description": f"Validate the leading alternative and size the ~{migration_months}-month migration."},
                    {"phase": "Final negotiation (alternative vs incumbent)", "duration": "1–2 weeks", "owners": ["Procurement", "Finance"], "description": "Compare best-and-final offers on 3-year total cost."},
                    {"phase": "Selection, approval and migration plan", "duration": "1 week", "owners": ["IT leadership", "Finance", "Legal"], "description": "Approve the selected vendor and sign off the transition plan."},
                ]

            # Notice-driven first step
            if dossier.notice_passed:
                steps.insert(0, {"phase": "Exit-options review (notice missed)", "duration": "Immediately", "owners": ["Legal", "Procurement"],
                                 "description": f"Notice deadline {dossier.notice_deadline} has passed. Confirm termination rights and bridge or early-exit options before term end {dossier.renewal_deadline}."})
            elif dossier.notice_at_risk and dossier.primary_decision != "Renew":
                steps.insert(0, {"phase": "Serve conditional non-renewal notice", "duration": "Immediately", "owners": ["Legal", "Procurement"],
                                 "description": f"Due by {dossier.notice_deadline} ({dossier.days_to_notice} days left). Preserves exit rights while negotiation continues."})

            notice_label = (f"Notice deadline ({dossier.notice_period_days} days) — MISSED" if dossier.notice_passed
                            else f"Notice deadline ({dossier.notice_period_days} days)")
            dossier.timeline = {
                "total_duration": duration,
                "steps": steps,
                "milestones": [
                    {"milestone": "Assessment initiated", "date": dossier.as_of.isoformat(), "critical": False},
                    {"milestone": notice_label, "date": dossier.notice_deadline, "critical": True},
                    {"milestone": "Contract renewal", "date": dossier.renewal_deadline, "critical": False}
                ]
            }
            return f"{dossier.primary_decision} timeline: {len(steps)} phases, {duration}"

        self.execute_action("A7", "BuildExecutionTimeline", action_a7)

        # ----------------------------------------------------
        # Action A8: Assemble Final Executive Brief
        # ----------------------------------------------------
        def action_a8():
            dossier.brief = {
                "meta": {
                    "case_id": dossier.case_id,
                    "assessment_date": dossier.as_of.isoformat(),
                    "policy_version": dossier.policy_version,
                    "policy": dossier.policy.model_dump(),
                    "rule_checks": dossier.rule_checks,
                    "decided_by": self._decided_by(dossier),
                    "renewal_deadline": dossier.renewal_deadline,
                    "notice_deadline": dossier.notice_deadline,
                    "notice_days": dossier.notice_period_days,
                    "days_to_notice": dossier.days_to_notice,
                    "current_term_months": dossier.current_term_months,
                    "notice_at_risk": dossier.notice_at_risk,
                    "notice_passed": dossier.notice_passed,
                    "notice_status": dossier.notice_status,
                    "auto_renewal": dossier.auto_renewal,
                    "renewal_type": dossier.renewal_type,
                    "decision": dossier.primary_decision,
                    "decision_question": dossier.decision_question,
                    "success_criteria": dossier.success_criteria,
                    "confidentiality": "CONFIDENTIAL · EXECUTIVE BRIEF"
                },
                "vendor": {
                    "name": dossier.vendor_name,
                    "service": dossier.service_type,
                    "proposed_term_months": dossier.proposed_term_months,
                    "account_manager": raw["vendor"]["account_manager"],
                    "replacement_difficulty": replacement_difficulty,
                    "migration_estimate_months": migration_months,
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
                    "budget_gap_usd": dossier.budget_gap_usd,
                    "price_cap_pct": dossier.price_cap_pct,
                    "cap_breach": dossier.cap_breach,
                    "capped_acv": dossier.capped_acv
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
                    "proposed_unit_price": dossier.proposed_unit_price,
                    "proposed_seats": dossier.proposed_seats,
                    "seat_change": dossier.seat_change,
                    "added_modules": dossier.added_modules,
                    "removed_modules": dossier.removed_modules
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
                    "drivers": dossier.decision_drivers,
                    "switch_downgraded": dossier.switch_downgraded,
                    "options": dossier.strategic_options,
                    "negotiation_objectives": dossier.negotiation_objectives,
                    "fallback": dossier.fallback_strategy
                },
                "timeline": dossier.timeline,
                "sla_addendum_flags": dossier.addenda_flags
            }
            return f"Assembled executive brief with {len(dossier.brief)} sections"

        self.execute_action("A8", "AssembleFinalDecisionBrief", action_a8)

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=f"Synthesized decision: {dossier.primary_decision} (Risk: {dossier.risk_level}, Target: {_fmt_usd(dossier.negotiation_target_acv)})."
        )
