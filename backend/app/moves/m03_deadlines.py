"""
Move M03: Check Renewal Deadlines (Verb: Verify)
Computes contract renewal deadlines, non-renewal notice cutoff dates, and evaluates auto-renewal traps.
"""
from typing import Any
from datetime import timedelta
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
        msa = raw["msa"]

        # ----------------------------------------------------
        # Action A1: Extract Term End and Notice Requirements
        # ----------------------------------------------------
        def action_a1():
            dossier.renewal_deadline = msa["current_term_end"].isoformat()
            dossier.notice_period_days = msa["notice_period_days"]
            dossier.auto_renewal = msa["auto_renewal"]
            return f"Term End: {dossier.renewal_deadline}, Required Notice: {dossier.notice_period_days} days"

        self.execute_action("A1", "ExtractNoticeRules", action_a1)

        # ----------------------------------------------------
        # Action A2: Compute Notice Cutoff Date
        # ----------------------------------------------------
        def action_a2():
            notice_dt = msa["current_term_end"] - timedelta(days=dossier.notice_period_days)
            dossier.notice_deadline = notice_dt.isoformat()
            dossier.days_to_notice = (notice_dt - dossier.as_of).days

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
        days = dossier.days_to_notice
        dossier.notice_passed = days < 0
        is_imminent = 0 <= days <= 21
        dossier.notice_at_risk = is_imminent

        if dossier.notice_passed:
            notice_status = "AUTO_RENEWED_LOCK_IN" if dossier.auto_renewal else "NOTICE_WINDOW_CLOSED"
            details = f"Notice cutoff passed {abs(days)} days ago ({dossier.notice_deadline})."
        elif is_imminent:
            notice_status = "IMMINENT_RISK"
            details = f"{days} days remaining until notice cutoff."
        else:
            notice_status = "ADEQUATE_RUNWAY"
            details = f"{days} days remaining until notice cutoff."
        dossier.notice_status = notice_status

        self.record_gate(
            "G2",
            "NoticeUrgencyGate",
            passed=True,
            decision=notice_status,
            details=details
        )

        # ----------------------------------------------------
        # Action A4: Urgent Notice Alert Dispatch
        # ----------------------------------------------------
        if is_imminent:
            def action_a4():
                return f"CRITICAL: Notice cutoff is in {dossier.days_to_notice} days ({dossier.notice_deadline}). Immediate legal notice required."
            self.execute_action("A4", "GenerateEmergencyNoticeWarning", action_a4)
        elif dossier.notice_passed:
            def action_a4():
                if dossier.auto_renewal:
                    return (f"MISSED: Notice cutoff {dossier.notice_deadline} passed {abs(days)} days ago; "
                            "the auto-renewal clause will roll the contract into a new term. Exit now requires vendor agreement or a termination right.")
                return (f"MISSED: Notice cutoff {dossier.notice_deadline} passed {abs(days)} days ago; "
                        "no auto-renewal, so the contract lapses at term end unless renewed.")
            self.execute_action("A4", "GenerateMissedNoticeWarning", action_a4)
        else:
            self.skip_action("A4", "GenerateEmergencyNoticeWarning", f"Notice cutoff is {dossier.days_to_notice} days out; within normal planning runway.")

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=f"Notice cutoff: {dossier.notice_deadline}. Status: {dossier.notice_status}."
        )
