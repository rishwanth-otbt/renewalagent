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
        usage = raw.get("usage", {})
        pricing = raw.get("current_pricing", {})

        # ----------------------------------------------------
        # Action A1: Extract License Inventory & Department Activity
        # ----------------------------------------------------
        def action_a1():
            dossier.total_provisioned_seats = int(pricing.get("total_seats", usage.get("total_provisioned_seats", 0)))
            dossier.active_seats = int(usage.get("active_seats_last_90_days", 0))
            dossier.inactive_seats = max(0, dossier.total_provisioned_seats - dossier.active_seats)
            return f"Provisioned: {dossier.total_provisioned_seats:,}, Active: {dossier.active_seats:,}, Inactive: {dossier.inactive_seats:,}"

        self.execute_action("A1", "ExtractSeatInventory", action_a1)

        # ----------------------------------------------------
        # Action A2: Calculate Utilization Rate
        # ----------------------------------------------------
        def action_a2():
            if dossier.total_provisioned_seats > 0:
                dossier.utilization_pct = round((dossier.active_seats / dossier.total_provisioned_seats) * 100, 1)
            else:
                dossier.utilization_pct = 100.0
            return f"Active Seat Utilization: {dossier.utilization_pct}%"

        self.execute_action("A2", "CalculateUtilizationRate", action_a2)

        # ----------------------------------------------------
        # Gate G1: Shelfware Detection Check
        # ----------------------------------------------------
        has_shelfware = dossier.utilization_pct < 90.0
        dossier.has_shelfware = has_shelfware
        
        self.record_gate(
            "G1",
            "ShelfwareDetectionGate",
            passed=True,
            decision="SHELFWARE_DETECTED" if has_shelfware else "OPTIMAL_UTILIZATION",
            details=f"Utilization is {dossier.utilization_pct}% (Threshold: 90.0%)."
        )

        # ----------------------------------------------------
        # Action A3: Quantify Shelfware & Financial Waste
        # ----------------------------------------------------
        if has_shelfware:
            def action_a3():
                unit_price = dossier.proposed_unit_price or dossier.current_unit_price
                # Modeled buffer of 9% above active seats
                dossier.recommended_seats = min(dossier.total_provisioned_seats, int(round(dossier.active_seats * 1.09)))
                dossier.reduction_opportunity = max(0, dossier.total_provisioned_seats - dossier.recommended_seats)
                dossier.annualized_waste_usd = round(dossier.reduction_opportunity * unit_price, 2)
                return f"{dossier.reduction_opportunity:,} inactive seats represent ${dossier.annualized_waste_usd:,.0f} in annual exposure"
            self.execute_action("A3", "QuantifyShelfwareExposure", action_a3)
        else:
            self.skip_action("A3", "QuantifyShelfwareExposure", "Active utilization is >= 90%; no material shelfware detected.")

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

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=f"Utilization: {dossier.utilization_pct}%. Recommended seats: {dossier.recommended_seats:,} (Reduction: {dossier.reduction_opportunity:,})."
        )
