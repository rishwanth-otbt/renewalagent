# Kozmo Move Architecture Specification (POC 2)

## 1. Executive Summary

This document specifies the technical architecture, execution semantics, and graph topology of the **Kozmo Renewal Desk Engine** implemented in POC 2.

Unlike a traditional linear state machine (where every state must run sequentially in a rigid waterfall), Kozmo models a procurement/renewal workflow as a **directed graph of Moves, Actions, and Gates**:
- **Moves** represent major cognitive steps (e.g., *Frame*, *Research*, *Verify*, *Evaluate*, *Analyze*, *Model*).
- **Actions** represent discrete, executable units of business logic (Python functions).
- **Gates** represent conditional evaluation checkpoints that inspect intermediate facts and dynamically decide whether downstream action nodes should **execute** or be **skipped**.
- **Dossier** acts as the central typed repository of facts and outcomes across the entire lifecycle.

```
                      RAW CONTRACT JSON INTAKE
                                │
                                ▼
 ┌─────────────────────────────────────────────────────────────┐
 │                RENEWAL DESK ORCHESTRATOR                    │
 │                                                             │
 │   [M01: Set Renewal Goals]            (Verb: Frame)         │
 │           │  (Gates: G0, G1 -> conditionally skips A4)      │
 │           ▼                                                 │
 │   [M02: Check Agreement Terms]        (Verb: Research)      │
 │           │  (Gates: G1, G2 -> conditionally skips A3, A4)  │
 │           ▼                                                 │
 │   [M03: Check Renewal Deadlines]      (Verb: Verify)        │
 │           │  (Gates: G1, G2 -> conditionally skips A3, A4)  │
 │           ▼                                                 │
 │   [M04: Assess Supplier Performance]  (Verb: Evaluate)      │
 │           │  (Gates: G1, G2 -> conditionally skips A3, A4)  │
 │           ▼                                                 │
 │   [M05: Analyze License & Usage]      (Verb: Analyze)       │
 │           │  (Gates: G1, G2 -> conditionally skips A3..A5)  │
 │           ▼                                                 │
 │   [M10: Model Costs & Recommend]      (Verb: Model)         │
 │              (Gate: G_DECIDE -> Route Renew / Reneg /       │
 │               Switch -> selectively builds A4 / A5 / A6)    │
 └──────────────────────────────┬──────────────────────────────┘
                                │
            ┌───────────────────┴───────────────────┐
            ▼                                       ▼
 ┌──────────────────────────┐            ┌─────────────────────┐
 │   EXECUTIVE BRIEF JSON   │            │   MOVE TRACE JSON   │
 │  (6 Section Brief Spec)  │            │  (Audited Graph)    │
 └──────────┬───────────────┘            └──────────┬──────────┘
            │                                       │
            ▼                                       ▼
  Browser Template Render                 Interactive Move Flow
  (KPIs, Tables, Risk, Timeline)          Modal (Actions & Gates)
```

---

## 2. Core Concepts & Data Structures

### 2.1 BaseMove (`backend/app/core/base_move.py`)
Every move inherits from `BaseMove` and implements:
```python
class BaseMove:
    move_id: str
    name: str
    verb: str

    def execute_action(self, action_id, name, fn, format_output=None) -> Any:
        # Measures execution time in milliseconds
        # Captures return value summary
        # Sets ActionStatus.EXECUTED

    def skip_action(self, action_id, name, reason: str):
        # Bypasses execution
        # Records duration = 0.0ms
        # Sets ActionStatus.SKIPPED and records skip_reason

    def record_gate(self, gate_id, name, passed: bool, decision: str, details=None) -> GateTrace:
        # Records gate condition and decision into move trace
```

### 2.2 Trace Dataclasses
Execution is strictly audited so the frontend can reconstruct what ran and why:
- `ActionTrace`: `id`, `name`, `status` (`EXECUTED` | `SKIPPED` | `FAILED`), `duration_ms`, `output_summary`, `skip_reason`.
- `GateTrace`: `id`, `name`, `passed` (bool), `decision` (str), `details` (str).
- `MoveTrace`: `move_id`, `name`, `verb`, `status`, `actions` (list), `gates` (list), `summary` (str).

### 2.3 The Central Dossier (`backend/app/core/dossier.py`)
The `Dossier` holds cumulative structured facts extracted and computed by each move:
- `raw_data`: Input contract JSON.
- `owner`, `decision_question`, `budget_ceiling`, `success_criteria` (from M01).
- `vendor_name`, `service_name`, `current_acv`, `proposed_acv`, `term_months` (from M02).
- `notice_deadline`, `notice_days`, `auto_renew_clause`, `notice_at_risk` (from M03).
- `uptime_contracted`, `uptime_actual`, `outages`, `service_credits_unclaimed` (from M04).
- `seats_total`, `seats_active`, `utilization_pct`, `shelfware_detected`, `recommended_seats` (from M05).
- `brief`: The slim final JSON ready for UI rendering (assembled by M10).

---

## 3. The 6 Implemented Moves

### Move M01: Set Renewal Goals (Verb: Frame)
- **Purpose**: Establishes who owns the renewal, the core decision question, authorized budget limits, and success criteria.
- **Actions**:
  - `A1`: Identify Renewal Owner & Stakeholder (`it_owner`, `business_sponsor`).
  - `A2`: Define Core Renewal Decision Question.
  - `A3`: Define Success Criteria (e.g., cost cap, terms protection).
  - `A4_Clarification`: Flag Information Gaps (*Skipped* if owner and budget ceiling are already present).
  - `A5`: Authorize Internal Mandate.
- **Gates**:
  - `G0`: *AuthorityBoundaryCheck* — confirms internal mandate scope.
  - `G1`: *BudgetCeilingDefinedCheck* — checks if `budget_cap` exists. If present, skips `A4_Clarification`.

### Move M02: Check Agreement Terms (Verb: Research)
- **Purpose**: Establishes baseline pricing, term durations, addenda commitments, and termination rights.
- **Actions**:
  - `A1`: Extract Agreement Baseline (MSA start date, term months, current ACV).
  - `A2`: Extract Pricing Structure (base license fee, support tier, unit seat costs).
  - `A3`: Audit Active Addenda & Side Letters (*Skipped* if contract has zero active addenda).
  - `A4`: Audit Expired Commitments (*Skipped* if zero expired addenda).
  - `A5`: Verify Termination & Renewal Rights.
- **Gates**:
  - `G1`: *ActiveAddendaCheck* — evaluates whether active amendments require auditing.
  - `G2`: *ExpiredCommitmentsCheck* — evaluates whether legacy clauses carry forward.

### Move M03: Check Renewal Deadlines (Verb: Verify)
- **Purpose**: Calculates critical notice cutoffs, detects auto-renewal traps, and raises alerts.
- **Actions**:
  - `A1`: Compute Required Notice Date (`renewal_deadline` minus `notice_days`).
  - `A2`: Check Auto-Renewal Mechanism (evaluates contract clause).
  - `A3`: Flag Auto-Renewal Trap Details (*Skipped* if auto-renewal is false).
  - `A4`: Raise Imminent Notice Risk Alert (*Skipped* if notice runway > 60 days).
- **Gates**:
  - `G1`: *AutoRenewalClauseCheck* — gates `A3`.
  - `G2`: *NoticeRunwaySufficiencyCheck* — gates `A4`.

### Move M04: Assess Supplier Performance (Verb: Evaluate)
- **Purpose**: Audits SLA uptime compliance, incident records, service credits, and roadmap deliveries.
- **Actions**:
  - `A1`: Audit SLA Availability & Uptime (`uptime_actual` vs `uptime_contracted`).
  - `A2`: Audit Support Ticket SLA Achievement.
  - `A3`: Investigate Production Incidents & Outages (*Skipped* if critical outages = 0).
  - `A4`: Claim Service Credit Compensation (*Skipped* if unclaimed credits = $0).
  - `A5`: Audit Product Roadmap Delivery (delays vs contracted deliverables).
  - `A6`: Score Supplier Overall Performance (Good / Acceptable / Sub-standard).
- **Gates**:
  - `G1`: *OutageForensicsGate* — gates `A3`.
  - `G2`: *ServiceCreditReclamationGate* — gates `A4`.

### Move M05: Analyze Usage & License Needs (Verb: Analyze)
- **Purpose**: Analyzes provisioned seats against active usage, flags shelfware, and calculates right-sized cost exposure.
- **Actions**:
  - `A1`: Compute Seat Utilization Rate (`active_seats / total_seats`).
  - `A2`: Classify Inactive Seat Cohort (90+ day dormant accounts).
  - `A3`: Detect License Shelfware (*Skipped* if utilization ≥ 90%).
  - `A4`: Model Right-Sized Baseline (*Skipped* if utilization ≥ 90%).
  - `A5`: Confirm Optimal Seat Capacity (*Skipped* if shelfware detected).
- **Gates**:
  - `G1`: *SeatAdoptionHealthyGate* — true if adoption ≥ 90%. Skips `A3` & `A4`.
  - `G2`: *ShelfwareRemediationGate* — true if inactive seats > 0. Skips `A5`.

### Move M10: Model Costs & Recommend (Verb: Model & Recommend)
- **Purpose**: Synthesizes facts from M01–M05, benchmarks price asks, evaluates risks, routes strategic decision via gate, and constructs final brief.
- **Actions**:
  - `A1`: Calculate 3-Year Commercial Exposure (Baseline vs Vendor Proposal vs Target).
  - `A2`: Benchmark Historical Renewal Trajectory (avg past increase vs current ask).
  - `A3`: Synthesize Cross-Domain Risk Register (Pricing, Operational, SLA, Notice risks).
  - `A4_Renew`: Build Renew Strategy Package (*Executed only if decision == RENEW*).
  - `A5_Renegotiate`: Build Renegotiation Strategy Package (*Executed only if decision == RENEW_WITH_RENEGOTIATION*).
  - `A6_Switch`: Build Switch / Benchmark Strategy Package (*Executed only if decision == SWITCH_OR_BENCHMARK*).
  - `A7`: Assemble Final Executive Decision Brief JSON.
- **Gates**:
  - `G_DECIDE`: Strategic Decision Routing Gate:
    - If `uptime_actual < 99.0%` or `critical_incidents >= 3` ➔ **ROUTE_SWITCH_BENCHMARK** (Executes `A6`, skips `A4`, `A5`).
    - If `price_increase_pct <= 5.0%` AND `utilization >= 90%` AND `budget_gap <= 0` ➔ **ROUTE_RENEW** (Executes `A4`, skips `A5`, `A6`).
    - Otherwise (e.g. shelfware, excessive price hike, over budget) ➔ **ROUTE_RENEGOTIATE** (Executes `A5`, skips `A4`, `A6`).

---

## 4. Orchestration Semantics (`RenewalDeskOrchestrator`)

The orchestrator executes sequentially through the moves:
```python
orchestrator = RenewalDeskOrchestrator()
result = orchestrator.run_play(raw_contract_json)
brief = result["brief"]
move_trace = result["move_trace"]
```
Because the `move_trace` is attached to `brief["meta"]["move_trace"]`, any API consumer receives the complete decision brief and the full graph execution trace in a single payload.
