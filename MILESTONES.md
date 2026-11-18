# Renewal Agent — Milestones

From POC1 (a fixed rule engine) to an agent that asks, analyses and keeps a living dossier.
**M1–M3 are the first release.** Each milestone ends with its "Done when" check passing.

| #  | Milestone                           | Done when                                                              |
| -- | ----------------------------------- | ---------------------------------------------------------------------- |
| M1 | Policy instead of hard-coded values | Changing "Renew at ≤ 7%" needs no code change                         |
| M2 | Agent asks questions                | A subscription with no MSA runs, and the agent asks for what's missing |
| M3 | Inbox and review room UI            | A simple renewal can be decided in 3 clicks                            |
| M4 | LLM reads documents                 | No hand-written JSON                                                   |
| M5 | Strategy and what-if                | "What if 10% off?" returns updated numbers and trade-offs              |
| M6 | Research and opinions               | Large renewals get a benchmark automatically                           |
| M7 | Living dossier                      | The dossier updates itself when the vendor replies                     |
| M8 | Wider scope                         | Contracts, subscriptions, leases and contractors are all covered       |

Rules for every milestone:

- Local commit after each step; never push.
- Backend tests pass before a step is called done.
- Code computes the numbers and makes the final decision; an LLM (from M4) only reads, researches and writes.

---

## M1 — Policy instead of hard-coded values

**Goal:** every threshold the moves use comes from a client-owned, versioned policy instead of a number in the code.
The default policy equals today's values, so cases 001–004 give the same results after the change.

### Today's problem

- 28 decision thresholds and 4 fixed text values are literals across `m01`, `m03`, `m04`, `m05`, `m10`.
- Duplicates: the SLA rule (75% / 3 incidents / 0.15 gap) is in both `m04_performance.py:122` and `m10_recommend.py:155`; the 21-day notice window is in both M03 and M10.
- The brief cannot say which rule decided the label.

### Steps

- [x] **1. Safety net** — golden tests that record today's results for cases 001–004 (label, risk level, increase %, budget gap, rating, negotiation target).
- [x] **2. Policy model** — `app/models/policy_models.py`: `RenewalPolicy` (Pydantic) with groups `renew`, `switch`, `budget`, `performance`, `licenses`, `deadlines`, `risk`; defaults = today's values; validator rejects contradictions (e.g. renew limit ≥ switch trigger, poor SLA ≥ good SLA).
- [x] **3. Policy store** — `app/core/policy_store.py`: `load_current()` (latest version or defaults), `save(policy, saved_by)` (validate, next version, keep history). Files in `backend/policies/` — **not** `backend/data/`, which `/api/cases` lists as cases.
- [x] **4. Wire it in** — `Dossier.policy` field (section 0); `run_play(raw, as_of, policy=None)` loads the current policy.
- [x] **5. Replace literals, one move at a time** (golden tests green after each):
  - [x] M04 rating (`m04_performance.py:122-127`)
  - [x] M05 utilization target and buffer (`m05_licenses.py:46, 64`)
  - [x] M03 urgent-notice window (`m03_deadlines.py:71`)
  - [x] M10 routing, switching cost, budget target, risk register (`m10_recommend.py:15-16, 75-80, 134-182, 220-222`)
  - [x] M01 utilization criterion text (`m01_goals.py:87`)
- [x] **6. Remove duplicates** — M10's SLA risk uses M04's `performance_rating`; delete `NOTICE_URGENT_DAYS`, `HARD_TO_REPLACE_LEVELS`, `LONG_MIGRATION_MONTHS` constants.
- [x] **7. Policy-aware wording** — brief text prints policy values (e.g. "above the 90% threshold" at `m10_recommend.py:286`).
- [x] **8. Explain the decision** — brief gets `meta.policy_version` and `meta.rule_checks` (rule, actual value, passed).
- [x] **9. API** — `GET /api/policy`, `PUT /api/policy` (422 on invalid), `GET /api/policy/history`, `POST /api/policy/preview` (run all cases with a draft policy, no save).
- [x] **10. Frontend** — Policy button → settings page (grouped dropdowns, defaults shown, impact preview, save); first-run wizard; rule-check strip under the decision.
- [x] **11. Small fixes found in review**
  - [x] Financial table: proposed seats show current seats and "0% (Hold volume)" is fixed text (`frontend/app.js:354-356`).
  - [x] Per-seat delta always prints "+" (`frontend/app.js:362`).
  - [x] M10 A2 trace "Current ask is 7.6% vs avg" should say percentage points above average.

### Tests

- [x] Golden: default policy = today's results for all 4 cases.
- [x] Boundaries: 5.0% passes Renew, 5.1% does not; 30.0% is Switch; 90.0% utilization is not shelfware; 21 days is urgent, 22 is not.
- [x] Policy change: switch trigger 20% → case 001 becomes Switch; renew limit 25% → case 001 stays Renegotiate (rating and budget still fail).
- [x] Validation: contradictory policies are rejected with clear messages.
- [x] Uncovered paths get sample cases: G2 downgrade (hard-to-replace, acceptable performance), seat expansion, no approved budget, safe notice window.

### Status

Implemented on branch `feature/m1-policy-config` (one local commit per step). 104 backend tests pass.
The "Renew at ≤ 7%" check was verified through `PUT /api/policy` (the call the settings page makes) and sample 17;
the settings page was checked visually, not by an automated click-through.

### Done when

- [x] Changing "Renew at ≤ 7%" in the settings page changes results with **no code change**.
- [x] No threshold literal is left in `backend/app/moves/`.
- [x] Every brief shows the policy version and the rules that decided it.

---

## M2 — Agent asks questions

**Goal:** the agent pauses on a real gap or decision, asks with selectable options, and resumes with the answer.

### Deliverables

- [ ] Move state `WAITING` with a question object: `id`, `text`, `options[]`, `recommended`, `why`.
- [ ] Orchestrator can pause and `resume(case_id, answer)` from the waiting move (pattern from `Appendix/creationmoves/M01_Set_Renewal_Goals`).
- [ ] `POST /api/case/{id}/answer`; answers saved with who and when.
- [ ] UI question cards: options as buttons, recommended option marked, "Other" free text.
- [ ] Template v2:
  - [ ] `renewal_kind`: contract · subscription · lease · contractor · service.
  - [ ] Small required core: vendor, product, annual cost, renewal date, owner.
  - [ ] Other sections optional; a missing value becomes a question or a flag, not a 422.
  - [ ] Each value can carry its source (document, page, "user answered").
- [ ] First question set: missing budget, unused seats (cut or growth expected?), bundled modules (needed?), unknown notice period, run a benchmark for large renewals?

### Done when

- [ ] A subscription with no MSA runs end to end, and the agent asks for what's missing.
- [ ] No question is asked when the data already answers it.

---

## M3 — Inbox and review room UI

**Goal:** simple renewals are decided fast; important ones get a full working view.

### Deliverables

- [ ] Left sidebar: Renewal Inbox · Review Room · Policy Settings (Deal Room later).
- [ ] Inbox cards: vendor, annual cost, deadline, recommendation; actions Renew / Review / Cancel.
- [ ] Review room: dossier in the centre (today's brief becomes its summary page); agent panel on the right with question cards and outputs.
- [ ] Move trace kept as a "how I got here" panel.
- [ ] Depth by value: low-value renewals stay in the inbox path.

### Done when

- [ ] A simple renewal can be decided in 3 clicks.
- [ ] A new user understands the page without a walkthrough.

---

## M4 — LLM reads documents(OCR)

**Goal:** upload real documents instead of writing JSON.

### Deliverables

- [ ] Upload quote, contract, amendments, invoices, usage exports.
- [ ] LLM extracts into the template with structured output (JSON schema), each value with its source page.
- [ ] Review screen: a human confirms or corrects each extracted field before the run.
- [ ] Extraction done once per document and cached in the dossier.
- [ ] Smaller model for extraction; code validates every value.

### Done when

- [ ] A case runs from uploaded documents with no hand-written JSON.
- [ ] Every number in the brief traces to a document or a user answer.

---

## M5 — Strategy and what-if

**Goal:** the agent proposes strategies and answers "what if" questions with numbers.

### Deliverables

- [ ] Price-increase breakdown: seats, unit price, added modules, other.
- [ ] Three-year cost per strategy (proposed, renegotiated, downsized, switch).
- [ ] Options A/B/C with trade-offs, risks and recommended choice.
- [ ] What-if simulator: discount %, term length, remove a module or support tier, seat count. LLM turns the question into inputs; code computes the result.
- [ ] Charts for scenarios in the review room.

### Done when

- [ ] "What if 10% off?" returns updated numbers and trade-offs.
- [ ] Every option shows its assumptions.

---

## M6 — Research and opinions

**Goal:** important renewals get outside evidence and internal input automatically.

### Deliverables

- [ ] Competitor and market research with cited sources and an as-of date.
- [ ] Pricing benchmarks where sources allow.
- [ ] Stakeholder survey to IT, Finance, Security and users; answers feed the dossier.
- [ ] Analysis depth and spend set by deal value in the policy (light · standard · deep).

### Done when

- [ ] Renewals above the "deep" threshold get a benchmark without being asked.
- [ ] Every research claim links to its source.

---

## M7 — Living dossier

**Goal:** the dossier is saved, versioned and kept current.

### Deliverables

- [ ] Dossier, brief, inputs and trace saved per version (database instead of JSON files).
- [ ] New information (vendor reply, usage update, answer) reruns only the affected moves.
- [ ] Draft vendor counter-offer and negotiation plan.
- [ ] Final contract checked against agreed terms.
- [ ] History view: what changed between versions and why.

### Done when

- [ ] The dossier updates itself when the vendor replies.
- [ ] Any past decision can be reopened with the inputs and policy it used.

---

## M8 — Wider scope

**Goal:** cover every kind of recurring spend that needs a renewal decision.

### Deliverables

- [ ] Discover subscriptions from accounts payable and card spend.
- [ ] Renewal kinds beyond contracts: subscriptions, equipment leases, contractors, services.
- [ ] Deal room for multi-department decisions.
- [ ] Portfolio view: overlapping tools across departments, extend-existing-contract suggestions.
- [ ] Same dossier approach reused in Contract Desk.
- [ ] Production basics: authentication, restricted CORS, audit log.

### Done when

- [ ] Contracts, subscriptions, leases and contractors are all managed in one place.
