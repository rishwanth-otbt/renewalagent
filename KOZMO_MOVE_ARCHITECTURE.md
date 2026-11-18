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
 │              (Gates: G1 route + G2 switching cost ->         │
 │               Renew / Reneg / Switch -> A4 / A5 / A6)       │
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
- **Purpose**: Calculates the notice cutoff, detects auto-renewal traps, and classifies the notice situation.
- **Actions**:
  - `A1`: Extract term end, notice period and auto-renewal flag.
  - `A2`: Compute notice cutoff (`current_term_end` minus `notice_period_days`) and `days_to_notice` relative to the assessment date (`as_of`).
  - `A3`: Flag Auto-Renewal Trap (*Skipped* if auto-renewal is false).
  - `A4`: `GenerateEmergencyNoticeWarning` if 0–21 days remain, or `GenerateMissedNoticeWarning` if the cutoff has passed (*Skipped* otherwise).
- **Gates**:
  - `G1`: *AutoRenewalClauseCheck* → `AUTO_RENEWAL_ACTIVE` | `MANUAL_RENEWAL_ONLY`.
  - `G2`: *NoticeUrgencyGate* →
    - `AUTO_RENEWED_LOCK_IN`: cutoff passed and auto-renewal is on.
    - `NOTICE_WINDOW_CLOSED`: cutoff passed, no auto-renewal (contract lapses at term end).
    - `IMMINENT_RISK`: 0–21 days left.
    - `ADEQUATE_RUNWAY`: more than 21 days left.

### Move M04: Assess Supplier Performance (Verb: Evaluate)
- **Purpose**: Audits SLA uptime, support SLA, incidents, service credits and roadmap delivery.
- **Actions**: `A1` uptime & support SLA, `A2` outage count, `A3` outage impact (*Skipped* if 0 incidents), `A4` surface unclaimed credits (*Skipped* if $0), `A5` roadmap delivery, `A6` rating.
- **Rating (A6)**:
  - **Needs Improvement**: uptime gap > 0.15 pts, or support SLA < 75%, or ≥ 3 critical incidents.
  - **Good**: uptime gap ≤ 0.05 pts, support SLA ≥ 90% and 0 critical incidents.
  - **Acceptable**: everything else.
- **Gates**: `G1` *OutageSeverityCheck*, `G2` *ServiceCreditsEligibilityGate*.

### Move M05: Analyze Usage & License Needs (Verb: Analyze)
- **Purpose**: Analyzes seat usage, flags shelfware, sizes the right seat count, and classifies the renewal by volume and scope.
- **Actions**:
  - `A1`: Seat inventory. `A2`: Utilization (`active_seats_last_90_days / total_seats`).
  - `A3`: Quantify shelfware (recommended seats = active × 1.09) (*Skipped* if utilization ≥ 90%).
  - `A4`: Model right-sized baseline (*Skipped* if utilization ≥ 90%).
  - `A5`: Confirm full license retention (*Skipped* if shelfware detected).
  - `A6`: Challenge scope changes: seat expansion while seats are idle, and modules in the proposal that are not in the current agreement (*Skipped* if neither).
- **Gates**:
  - `G1`: *ShelfwareDetectionGate* → `SHELFWARE_DETECTED` if utilization < 90%.
  - `G2`: *RenewalVolumeTypeGate* → `RENEWAL_EXPANSION` | `RENEWAL_REDUCTION` | `RENEWAL_FLAT` (`proposed_seats` vs current `total_seats`).

### Move M10: Model Costs & Recommend (Verb: Model & Recommend)
- **Purpose**: Synthesizes M01–M05, models cost exposure, builds the risk register, routes the decision, and assembles the brief.
- **Actions**:
  - `A1`: 3-year exposure and negotiation target. If `msa.price_increase_cap_pct` is set and the increase exceeds it, `cap_breach = true` and the target is capped at `current_acv × (1 + cap)`.
  - `A2`: Historical benchmark (average past increase vs current ask).
  - `A3`: Risk register (price, cap breach, shelfware, unsupported expansion, bundled modules, SLA, term lock-in, no termination for convenience, roadmap, notice status). Risk level: ≥ 2 High → High; 1 High → Medium–High.
  - **Decision drivers**: the list of facts that moved the case away from a clean renewal (increase > 5%, cap breach, over budget, shelfware, rating below Good, bundled modules, unsupported expansion). Rationales are built from this list, not fixed text.
  - `A4_Renew` / `A5_Renegotiate` / `A6_Switch`: exactly one runs. Options, objectives and fallback are conditional on the case facts and on the M03 notice status.
  - `A7`: Decision-specific timeline (Renew 1–2 weeks, Renegotiate 4–6 weeks, Switch 8–12 weeks); an immediate notice or exit-options step is added first when notice is imminent or missed.
  - `A8`: Assemble the brief JSON.
- **Gates**:
  - `G1` *StrategicDecisionRoutingGate*:
    - `ROUTE_SWITCH_BENCHMARK` if increase ≥ 30%, OR (uptime gap > 0.5 pts AND rating Needs Improvement AND increase ≥ 20%).
    - `ROUTE_RENEW` if increase ≤ 5% AND rating Good AND within budget AND no cap breach.
    - `ROUTE_RENEGOTIATE` otherwise.
  - `G2` *SwitchingCostGate*: if routed to Switch, the vendor is hard to replace (`replacement_difficulty` High / Very High / Critical, or `migration_estimate_months` ≥ 12) and the rating is not Needs Improvement, the decision is **downgraded to Renegotiate** (benchmark used as leverage).


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
