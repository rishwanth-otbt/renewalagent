"""
Move M04: Assess Supplier Performance (Verb: Evaluate)
Audits availability SLA, support response, outage frequency, unclaimed service credits, and roadmap milestone delivery.
"""
from typing import Any
try:
    from backend.app.core.base_move import BaseMove, MoveTrace
except ImportError:
    from app.core.base_move import BaseMove, MoveTrace


class MoveM04AssessSupplierPerformance(BaseMove):
    move_id = "M04"
    name = "Assess Supplier Performance"
    verb = "EVALUATE"

    def run(self, dossier: Any) -> MoveTrace:
        raw = dossier.raw_data
        sla = raw.get("sla", {})
        roadmap = raw.get("roadmap", {})

        # ----------------------------------------------------
        # Action A1: Audit Uptime and Support Response SLAs
        # ----------------------------------------------------
        def action_a1():
            dossier.contracted_uptime = float(sla.get("contracted_uptime_pct", 99.9))
            dossier.actual_uptime = float(sla.get("actual_uptime_pct", 99.9))
            dossier.uptime_gap = round(dossier.contracted_uptime - dossier.actual_uptime, 2)
            dossier.support_sla_achievement = float(sla.get("actual_support_sla_achievement_pct", 100.0))
            return f"Uptime: {dossier.actual_uptime}% vs {dossier.contracted_uptime}% (Gap: {dossier.uptime_gap}%), Support SLA: {dossier.support_sla_achievement}%"

        self.execute_action("A1", "AuditUptimeAndSupportSLA", action_a1)

        # ----------------------------------------------------
        # Action A2: Audit Production Outages
        # ----------------------------------------------------
        def action_a2():
            dossier.critical_incidents_count = int(sla.get("critical_incidents_count", 0))
            return f"Recorded {dossier.critical_incidents_count} critical production outages"

        self.execute_action("A2", "AuditOutageIncidents", action_a2)

        # ----------------------------------------------------
        # Gate G1: Critical Outage Check
        # ----------------------------------------------------
        has_outages = dossier.critical_incidents_count > 0
        self.record_gate(
            "G1",
            "OutageSeverityCheck",
            passed=True,
            decision="OUTAGES_DETECTED" if has_outages else "ZERO_OUTAGES",
            details=f"Critical incidents: {dossier.critical_incidents_count}"
        )

        # ----------------------------------------------------
        # Action A3: Outage Penalty Forensics
        # ----------------------------------------------------
        if has_outages:
            def action_a3():
                details = sla.get("critical_incidents_detail", [])
                total_hours = sum(d.get("duration_hours", 0) for d in details)
                obs = f"{dossier.critical_incidents_count} critical production disruptions ({total_hours:.1f} hrs total downtime) impacted operations."
                dossier.performance_observations.append(obs)
                return obs
            self.execute_action("A3", "CalculateOutageImpact", action_a3)
        else:
            self.skip_action("A3", "CalculateOutageImpact", "Zero critical outages recorded during contractual term.")

        # ----------------------------------------------------
        # Gate G2: Unclaimed Service Credits Check
        # ----------------------------------------------------
        dossier.service_credits_available = float(sla.get("service_credits_available_usd", 0.0))
        has_credits = dossier.service_credits_available > 0
        
        self.record_gate(
            "G2",
            "ServiceCreditsEligibilityGate",
            passed=True,
            decision="CREDITS_AVAILABLE" if has_credits else "NO_CREDITS",
            details=f"Unclaimed credits: ${dossier.service_credits_available:,.0f}"
        )

        # ----------------------------------------------------
        # Action A4: Service Credits Reclamation
        # ----------------------------------------------------
        if has_credits:
            def action_a4():
                flag = {
                    "type": "Unclaimed Service Credits",
                    "detail": f"${dossier.service_credits_available:,.0f} in eligible SLA service credits currently unapplied — prime immediate leverage for ACV reduction."
                }
                dossier.addenda_flags.append(flag)
                return f"Surfaced ${dossier.service_credits_available:,.0f} in actionable SLA credits"
            self.execute_action("A4", "SurfaceUnclaimedServiceCredits", action_a4)
        else:
            self.skip_action("A4", "SurfaceUnclaimedServiceCredits", "No eligible unclaimed service credits on file.")

        # ----------------------------------------------------
        # Action A5: Audit Roadmap Delivery
        # ----------------------------------------------------
        def action_a5():
            milestones = roadmap.get("promised_milestones", [])
            dossier.roadmap_total_count = len(milestones)
            dossier.roadmap_delivered_count = sum(1 for m in milestones if m.get("delivered"))
            dossier.roadmap_delayed_features = [m.get("feature") for m in milestones if not m.get("delivered")]
            
            if dossier.roadmap_delayed_features:
                dossier.performance_observations.append(
                    f"{len(dossier.roadmap_delayed_features)} committed product roadmap features remain undelivered ({', '.join(dossier.roadmap_delayed_features)})."
                )
            else:
                dossier.performance_observations.append("All contracted feature roadmap commitments have been successfully delivered.")
            
            return f"Delivered {dossier.roadmap_delivered_count} of {dossier.roadmap_total_count} promised milestones"

        self.execute_action("A5", "AuditRoadmapDelivery", action_a5)

        # ----------------------------------------------------
        # Action A6: Synthesize Overall Performance Score
        # ----------------------------------------------------
        def action_a6():
            if dossier.uptime_gap > 0.15 or dossier.support_sla_achievement < 75.0 or dossier.critical_incidents_count >= 3:
                dossier.performance_rating = "Needs Improvement"
            elif dossier.uptime_gap <= 0.05 and dossier.support_sla_achievement >= 90.0 and dossier.critical_incidents_count == 0:
                dossier.performance_rating = "Good"
            else:
                dossier.performance_rating = "Acceptable"
            return f"Vendor Performance Rating: {dossier.performance_rating}"

        self.execute_action("A6", "ScorePerformanceRating", action_a6)

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETE",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary=f"Performance rating: {dossier.performance_rating} (Uptime: {dossier.actual_uptime}%, Outages: {dossier.critical_incidents_count})."
        )
