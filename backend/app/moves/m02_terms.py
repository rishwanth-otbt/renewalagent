"""
Move M02: Check Agreement Terms (Verb: Research)
Extracts contract baseline, term duration, pricing structure, active and expired addenda, and legal exit terms.
"""
from typing import Any
from datetime import datetime
try:
    from backend.app.core.base_move import BaseMove, MoveTrace
except ImportError:
    from app.core.base_move import BaseMove, MoveTrace


class MoveM02CheckAgreementTerms(BaseMove):
    move_id = "M02"
    name = "Check Agreement Terms"
    verb = "RESEARCH"

    def run(self, dossier: Any) -> MoveTrace:
        raw = dossier.raw_data
        vendor = raw.get("vendor", {})
        msa = raw.get("msa", {})
        current_pricing = raw.get("current_pricing", {})
        proposal = raw.get("vendor_proposal", {})
        addenda = raw.get("addendum", [])

        # ----------------------------------------------------
        # Action A1: Extract Contract Agreement Baseline
        # ----------------------------------------------------
        def action_a1():
            dossier.vendor_name = vendor.get("name", "Vendor")
            dossier.service_type = vendor.get("service_type", "SaaS Platform")
            dossier.contract_id = msa.get("contract_id", "N/A")
            dossier.proposed_term_months = int(proposal.get("proposed_term_months", 36))
            
            # Duration calculation
            start_str = msa.get("current_term_start", "2024-02-01")
            end_str = msa.get("current_term_end", "2027-01-31")
            try:
                dt_start = datetime.strptime(start_str, "%Y-%m-%d")
                dt_end = datetime.strptime(end_str, "%Y-%m-%d")
                dossier.current_term_months = max(1, round((dt_end - dt_start).days / 30.4))
            except Exception:
                dossier.current_term_months = 12

            return f"Vendor: {dossier.vendor_name}, Contract: {dossier.contract_id}, Current Term: {dossier.current_term_months}m"

        self.execute_action("A1", "ExtractAgreementBaseline", action_a1)

        # ----------------------------------------------------
        # Action A2: Extract Commercial Pricing Model
        # ----------------------------------------------------
        def action_a2():
            dossier.current_acv = float(current_pricing.get("annual_contract_value", 0.0))
            dossier.proposed_acv = float(proposal.get("proposed_annual_value", 0.0))
            dossier.current_unit_price = float(current_pricing.get("unit_price_per_seat", 0.0))
            dossier.proposed_unit_price = float(proposal.get("proposed_unit_price", 0.0))
            return f"Current ACV: ${dossier.current_acv:,.0f} -> Proposed ACV: ${dossier.proposed_acv:,.0f}"

        self.execute_action("A2", "ExtractPricingModel", action_a2)

        # ----------------------------------------------------
        # Gate G1: Check for Addenda Inventory
        # ----------------------------------------------------
        expired_addenda = [a for a in addenda if a.get("status") == "expired"]
        active_addenda = [a for a in addenda if a.get("status") == "active"]
        
        self.record_gate(
            "G1",
            "AddendaStatusCheck",
            passed=True,
            decision="PROCESS_ADDENDA" if addenda else "NO_ADDENDA",
            details=f"Active: {len(active_addenda)}, Expired: {len(expired_addenda)}"
        )

        # ----------------------------------------------------
        # Action A3: Inspect Active Addenda Governance
        # ----------------------------------------------------
        if active_addenda:
            def action_a3():
                flags = []
                for add in active_addenda:
                    flags.append({
                        "type": "Active Addendum Governance",
                        "detail": f"{add.get('addendum_id')}: {add.get('description')} must be carried over into renewed agreement."
                    })
                dossier.addenda_flags.extend(flags)
                return f"{len(flags)} active addenda recorded for carryover"
            self.execute_action("A3", "AuditActiveAddenda", action_a3)
        else:
            self.skip_action("A3", "AuditActiveAddenda", "No active addenda found in agreement inventory.")

        # ----------------------------------------------------
        # Action A4: Audit Expired Addenda & Re-pricing Exposure
        # ----------------------------------------------------
        if expired_addenda:
            def action_a4():
                flags = []
                for add in expired_addenda:
                    flags.append({
                        "type": "Expired Addendum Exposure",
                        "detail": f"{add.get('addendum_id')}: {add.get('description')} is expired. Verify no retroactive billing or unbundled pricing."
                    })
                dossier.addenda_flags.extend(flags)
                return f"{len(flags)} expired addenda flagged for re-pricing exposure"
            self.execute_action("A4", "AuditExpiredAddenda", action_a4)
        else:
            self.skip_action("A4", "AuditExpiredAddenda", "No expired addenda present in contract record.")

        # ----------------------------------------------------
        # Action A5: Audit Termination & Convenience Terms
        # ----------------------------------------------------
        def action_a5():
            dossier.termination_for_convenience = msa.get("termination_for_convenience", False)
            dossier.auto_renewal = msa.get("auto_renewal", True)
            status_desc = "Convenience Termination: YES" if dossier.termination_for_convenience else "Convenience Termination: NO (Lock-in risk)"
            return f"{status_desc}, Auto-Renewal: {dossier.auto_renewal}"

        self.execute_action("A5", "AuditTerminationRights", action_a5)

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=f"Agreement verified. Current ACV: ${dossier.current_acv:,.0f}, Proposed ACV: ${dossier.proposed_acv:,.0f}."
        )
