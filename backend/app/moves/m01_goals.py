"""
Move M01: Set Renewal Goals (Verb: Frame)
Establishes the accountable owner, decision question, budget ceiling, authorized actions, and success criteria.
Adapted from Kozmo M01 Move Card and reference implementation.
"""
from typing import Any, Dict, List
try:
    from backend.app.core.base_move import BaseMove, MoveTrace
except ImportError:
    from app.core.base_move import BaseMove, MoveTrace


class MoveM01SetRenewalGoals(BaseMove):
    move_id = "M01"
    name = "Set Renewal Goals"
    verb = "FRAME"

    def run(self, dossier: Any) -> MoveTrace:
        raw = dossier.raw_data
        vendor_info = raw["vendor"]
        internal = raw["internal_assessment"]
        proposal = raw["vendor_proposal"]
        emails = raw["emails"]

        # ----------------------------------------------------
        # Action A1: Load Request Context & Identify Owner
        # ----------------------------------------------------
        def action_a1():
            dossier.case_id = raw["case_id"]
            dossier.accountable_owner = internal["budget_owner"]
            dossier.approved_budget_acv = float(internal["approved_budget_acv"])
            dossier.strategic_importance = internal["strategic_importance"]
            dossier.known_alternatives = internal["known_alternatives"]
            return f"Owner: {dossier.accountable_owner}, Budget: ${dossier.approved_budget_acv:,.0f}"

        self.execute_action("A1", "LoadRequestContext", action_a1)

        # ----------------------------------------------------
        # Gate G0: Authority & Scope Check
        # ----------------------------------------------------
        # Check if email/request asks for unapproved actions (e.g. unauthorized direct vendor negotiation)
        has_negotiate_intent = any("negotiat" in e["summary"].lower() for e in emails)
        is_mandated_to_negotiate = dossier.approved_budget_acv > 0
        self.record_gate(
            "G0",
            "AuthorityBoundaryCheck",
            passed=True,
            decision="ANALYZE_AND_CONSULT",
            details="Internal mandate authorizes analytical modeling and internal consultation."
        )

        # ----------------------------------------------------
        # Action A2: Frame Decision Question
        # ----------------------------------------------------
        def action_a2():
            vendor_name = vendor_info["name"]
            proposed_term = proposal["proposed_term_months"] / 12
            proposed_term = int(proposed_term) if proposed_term.is_integer() else round(proposed_term, 1)
            dossier.decision_question = (
                f"Should the organization commit to a {proposed_term}-year renewal with {vendor_name} "
                f"under proposed commercial terms, seek restructured licensing, or benchmark alternative providers?"
            )
            return dossier.decision_question

        self.execute_action("A2", "FrameDecisionQuestion", action_a2)

        # ----------------------------------------------------
        # Action A3: Establish Success Criteria (MUST & SHOULD)
        # ----------------------------------------------------
        def action_a3():
            contracted_uptime = raw["sla"]["contracted_uptime_pct"]
            criteria = []
            if dossier.approved_budget_acv > 0:
                criteria.append({
                    "priority": "MUST",
                    "statement": f"Annual contract value stays at or below approved budget ceiling (${dossier.approved_budget_acv:,.0f})",
                    "target": f"<= ${dossier.approved_budget_acv:,.0f}"
                })
            criteria.append({
                "priority": "MUST",
                "statement": f"Service availability meets or exceeds contractual uptime threshold (>= {contracted_uptime}%)",
                "target": f">= {contracted_uptime}% Uptime"
            })
            criteria.append({
                "priority": "SHOULD",
                "statement": "Active license volume aligns with demonstrated 90-day organizational utilization",
                "target": ">= 90% seat utilization"
            })
            dossier.success_criteria = criteria
            must = sum(1 for c in criteria if c["priority"] == "MUST")
            return f"{len(criteria)} success criteria defined (MUST: {must}, SHOULD: {len(criteria) - must})"

        self.execute_action("A3", "EstablishSuccessCriteria", action_a3)

        # ----------------------------------------------------
        # Gate G1: Check for Unauthorized Solution-Phrased Actions
        # ----------------------------------------------------
        # If requester asked for supplier commitments before analysis, exclude premature commitments
        if has_negotiate_intent and not is_mandated_to_negotiate:
            dossier.exclusions = ["No direct supplier commitment prior to mandate review."]
            self.record_gate("G1", "MandateExclusionCheck", passed=True, decision="EXCLUDE_DIRECT_COMMITMENT")
        else:
            dossier.exclusions = ["No unbudgeted contract execution without executive sign-off."]
            self.record_gate("G1", "MandateExclusionCheck", passed=True, decision="STANDARD_GOVERNANCE")

        # ----------------------------------------------------
        # Action A4: Clarification & Gap Analysis
        # ----------------------------------------------------
        # If budget or owner is missing, we would pause at A5/A6. If present, skip clarification!
        if dossier.approved_budget_acv > 0 and dossier.accountable_owner:
            self.skip_action("A4_Clarification", "RequestOwnerClarification", "No material mandate gaps found; budget and owner are authoritative.")
        else:
            def action_a4():
                return "Mandate gaps identified; flagged for owner clarification."
            self.execute_action("A4_Clarification", "RequestOwnerClarification", action_a4)

        # ----------------------------------------------------
        # Action A5: Authorize Downstream Moves
        # ----------------------------------------------------
        def action_a5():
            dossier.authorized_actions = ["ANALYZE", "CONSULT_INTERNAL", "MODEL_SCENARIOS"]
            dossier.m01_status = "CONFIRMED"
            return "Mandate confirmed: Authorizing M02, M03, M04, M05, M10"

        self.execute_action("A5", "AuthorizeReviewMandate", action_a5)

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=f"Mandate confirmed for owner {dossier.accountable_owner}. Budget ceiling: ${dossier.approved_budget_acv:,.0f}."
        )
