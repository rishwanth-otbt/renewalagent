"""
Move M05: Analyze Usage & License Needs (Verb: Analyze & Model)
Audits active vs. inactive license seats across departments, calculates shelfware cost waste, and models optimized baselines.
"""
from typing import Any
try:
    from backend.app.core.base_move import BaseMove, MoveTrace
except ImportError:
    from app.core.base_move import BaseMove, MoveTrace


class MoveM05AnalyzeLicenseNeeds(BaseMove):
    move_id = "M05"
    name = "Analyze Usage & License Needs"
    verb = "ANALYZE"

    def run(self, dossier: Any) -> MoveTrace:
        raw = dossier.raw_data
        lic = dossier.policy.licenses
        usage = raw["usage"]
        pricing = raw["current_pricing"]

        # ----------------------------------------------------
        # Action A1: Extract License Inventory & Department Activity
        # ----------------------------------------------------
        def action_a1():
            dossier.total_provisioned_seats = pricing["total_seats"]
            dossier.active_seats = usage["active_seats_last_90_days"]
            dossier.inactive_seats = max(0, dossier.total_provisioned_seats - dossier.active_seats)
            return f"Provisioned: {dossier.total_provisioned_seats:,}, Active: {dossier.active_seats:,}, Inactive: {dossier.inactive_seats:,}"

        self.execute_action("A1", "ExtractSeatInventory", action_a1)

        # ----------------------------------------------------
        # Action A2: Calculate Utilization Rate
        # ----------------------------------------------------
        def action_a2():
            # total_seats > 0 is enforced by the input schema
            dossier.utilization_pct = round((dossier.active_seats / dossier.total_provisioned_seats) * 100, 1)
            return f"Active Seat Utilization: {dossier.utilization_pct}%"

        self.execute_action("A2", "CalculateUtilizationRate", action_a2)

        # ----------------------------------------------------
        # Gate G1: Shelfware Detection Check
        # ----------------------------------------------------
        has_shelfware = dossier.utilization_pct < lic.target_utilization_pct
        dossier.has_shelfware = has_shelfware
        
        self.record_gate(
            "G1",
            "ShelfwareDetectionGate",
            passed=True,
            decision="SHELFWARE_DETECTED" if has_shelfware else "OPTIMAL_UTILIZATION",
            details=f"Utilization is {dossier.utilization_pct}% (Threshold: {lic.target_utilization_pct:g}%)."
        )

        # ----------------------------------------------------
        # Action A3: Quantify Shelfware & Financial Waste
        # ----------------------------------------------------
        if has_shelfware:
            def action_a3():
                unit_price = dossier.proposed_unit_price
                # Right-sizing buffer above active seats (policy.licenses.seat_buffer_pct)
                factor = 1 + lic.seat_buffer_pct / 100
                dossier.recommended_seats = min(dossier.total_provisioned_seats, int(round(dossier.active_seats * factor)))
                dossier.reduction_opportunity = max(0, dossier.total_provisioned_seats - dossier.recommended_seats)
                dossier.annualized_waste_usd = round(dossier.reduction_opportunity * unit_price, 2)
                return f"{dossier.reduction_opportunity:,} inactive seats represent ${dossier.annualized_waste_usd:,.0f} in annual exposure"
            self.execute_action("A3", "QuantifyShelfwareExposure", action_a3)
        else:
            self.skip_action("A3", "QuantifyShelfwareExposure", f"Active utilization is >= {lic.target_utilization_pct:g}%; no material shelfware detected.")

        # ----------------------------------------------------
        # Action A4: Model Optimized Seat Baseline
        # ----------------------------------------------------
        if has_shelfware:
            def action_a4():
                obs = f"Active seat utilization is at {dossier.utilization_pct}%, indicating {dossier.inactive_seats:,} inactive seats available for reclamation."
                dossier.performance_observations.append(obs)
                return f"Right-sized baseline modeled at {dossier.recommended_seats:,} seats (holding {dossier.total_provisioned_seats - dossier.recommended_seats:,} reduction target)"
            self.execute_action("A4", "ModelRightSizedBaseline", action_a4)
        else:
            self.skip_action("A4", "ModelRightSizedBaseline", "Full license allocation retained; no volume reduction modeled.")

        # ----------------------------------------------------
        # Action A5: Confirm Full License Allocation
        # ----------------------------------------------------
        if not has_shelfware:
            def action_a5():
                dossier.recommended_seats = dossier.total_provisioned_seats
                dossier.reduction_opportunity = 0
                dossier.annualized_waste_usd = 0.0
                obs = f"High seat adoption across departments ({dossier.utilization_pct}% active utilization); full license allocation validated."
                dossier.performance_observations.append(obs)
                return f"Retained 100% of provisioned volume ({dossier.total_provisioned_seats:,} seats)"
            self.execute_action("A5", "ConfirmFullLicenseRetention", action_a5)
        else:
            self.skip_action("A5", "ConfirmFullLicenseRetention", "Shelfware detected; full volume retention rejected.")

        # ----------------------------------------------------
        # Gate G2: Renewal Volume Type (Expansion / Reduction / Flat)
        # ----------------------------------------------------
        proposal = raw["vendor_proposal"]
        dossier.proposed_seats = proposal["proposed_seats"]
        dossier.seat_change = dossier.proposed_seats - dossier.total_provisioned_seats
        if dossier.seat_change > 0:
            dossier.renewal_type = "EXPANSION"
        elif dossier.seat_change < 0:
            dossier.renewal_type = "REDUCTION"
        else:
            dossier.renewal_type = "FLAT"

        current_modules = pricing.get("modules_included") or []
        proposed_modules = proposal.get("proposed_modules") or []
        dossier.added_modules = [m for m in proposed_modules if m not in current_modules]
        dossier.removed_modules = [m for m in current_modules if m not in proposed_modules] if proposed_modules else []

        self.record_gate(
            "G2",
            "RenewalVolumeTypeGate",
            passed=True,
            decision=f"RENEWAL_{dossier.renewal_type}",
            details=(f"Proposed {dossier.proposed_seats:,} vs current {dossier.total_provisioned_seats:,} seats "
                     f"({dossier.seat_change:+,}); modules added: {len(dossier.added_modules)}, removed: {len(dossier.removed_modules)}.")
        )

        # ----------------------------------------------------
        # Action A6: Challenge Unsupported Expansion / Bundled Modules
        # ----------------------------------------------------
        expansion_unsupported = dossier.renewal_type == "EXPANSION" and dossier.has_shelfware
        if expansion_unsupported or dossier.added_modules:
            def action_a6():
                notes = []
                if expansion_unsupported:
                    obs = (f"Vendor proposes +{dossier.seat_change:,} seats while {dossier.inactive_seats:,} current seats are inactive; "
                           "expansion is not supported by usage.")
                    dossier.performance_observations.append(obs)
                    notes.append(obs)
                if dossier.added_modules:
                    flag = {
                        "type": "Bundled Module Change",
                        "detail": (f"Proposal adds {', '.join(dossier.added_modules)} not in the current agreement. "
                                   "Confirm the business requested it and get it priced separately from the renewal.")
                    }
                    dossier.addenda_flags.append(flag)
                    notes.append(flag["detail"])
                return " | ".join(notes)
            self.execute_action("A6", "ChallengeScopeChanges", action_a6)
        else:
            self.skip_action("A6", "ChallengeScopeChanges", "No unsupported seat expansion and no new modules in the proposal.")

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=(f"Utilization: {dossier.utilization_pct}%. Recommended seats: {dossier.recommended_seats:,} "
                     f"(Reduction: {dossier.reduction_opportunity:,}). Renewal type: {dossier.renewal_type}.")
        )
