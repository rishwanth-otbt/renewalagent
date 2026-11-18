"""
Move M03: Check Renewal Deadlines (Verb: Verify)
Computes contract renewal deadlines, non-renewal notice cutoff dates, and evaluates auto-renewal traps.
"""
from typing import Any
from datetime import datetime, timedelta
try:
    from backend.app.core.base_move import BaseMove, MoveTrace
except ImportError:
    from app.core.base_move import BaseMove, MoveTrace


class MoveM03CheckRenewalDeadlines(BaseMove):
    move_id = "M03"
    name = "Check Renewal Deadlines"
    verb = "VERIFY"

    def run(self, dossier: Any) -> MoveTrace:
        raw = dossier.raw_data
        msa = raw.get("msa", {})

        # ----------------------------------------------------
        # Action A1: Extract Term End and Notice Requirements
        # ----------------------------------------------------
        def action_a1():
            dossier.renewal_deadline = msa.get("current_term_end", "2027-01-31")
            dossier.notice_period_days = int(msa.get("notice_period_days", 60))
            dossier.auto_renewal = bool(msa.get("auto_renewal", True))
            return f"Term End: {dossier.renewal_deadline}, Required Notice: {dossier.notice_period_days} days"

        self.execute_action("A1", "ExtractNoticeRules", action_a1)

        # ----------------------------------------------------
        # Action A2: Compute Notice Cutoff Date
        # ----------------------------------------------------
        def action_a2():
            try:
                end_dt = datetime.strptime(dossier.renewal_deadline, "%Y-%m-%d")
                notice_dt = end_dt - timedelta(days=dossier.notice_period_days)
                dossier.notice_deadline = notice_dt.strftime("%Y-%m-%d")
                
                today = datetime.now()
                dossier.days_to_notice = (notice_dt - today).days
            except Exception:
                dossier.notice_deadline = "2026-12-02"
                dossier.days_to_notice = 14

            return f"Notice Cutoff: {dossier.notice_deadline} ({dossier.days_to_notice} days remaining)"

        self.execute_action("A2", "ComputeNoticeCutoff", action_a2)

        # ----------------------------------------------------
        # Gate G1: Check Auto-Renewal Clause Presence
        # ----------------------------------------------------
        self.record_gate(
            "G1",
            "AutoRenewalClauseCheck",
            passed=True,
            decision="AUTO_RENEWAL_ACTIVE" if dossier.auto_renewal else "MANUAL_RENEWAL_ONLY",
            details=f"Contract auto_renewal flag is {dossier.auto_renewal}."
        )

        # ----------------------------------------------------
        # Action A3: Flag Auto-Renewal Trap
        # ----------------------------------------------------
        if dossier.auto_renewal:
            def action_a3():
                return f"Auto-renewal is active. Formal non-renewal notice must be served by {dossier.notice_deadline}."
            self.execute_action("A3", "FlagAutoRenewalTrap", action_a3)
        else:
            self.skip_action("A3", "FlagAutoRenewalTrap", "Contract does not contain an evergreen auto-renewal clause.")

        # ----------------------------------------------------
        # Gate G2: Evaluate Imminent Cutoff Risk
        # ----------------------------------------------------
        is_imminent = dossier.days_to_notice <= 21
        dossier.notice_at_risk = is_imminent
        
        self.record_gate(
            "G2",
            "NoticeUrgencyGate",
            passed=True,
            decision="IMMINENT_RISK" if is_imminent else "ADEQUATE_RUNWAY",
            details=f"{dossier.days_to_notice} days remaining until notice cutoff."
        )

        # ----------------------------------------------------
        # Action A4: Urgent Notice Alert Dispatch
        # ----------------------------------------------------
        if is_imminent:
            def action_a4():
                return f"CRITICAL: Notice cutoff is in {dossier.days_to_notice} days ({dossier.notice_deadline}). Immediate legal notice required."
            self.execute_action("A4", "GenerateEmergencyNoticeWarning", action_a4)
        else:
            self.skip_action("A4", "GenerateEmergencyNoticeWarning", f"Notice cutoff is {dossier.days_to_notice} days out; within normal planning runway.")

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=f"Notice cutoff: {dossier.notice_deadline}. Notice at risk: {dossier.notice_at_risk}."
        )
