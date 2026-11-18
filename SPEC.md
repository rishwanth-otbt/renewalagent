# Renewal Desk — Spec

## 1. Purpose

Help a decision owner decide what to do with an IT vendor renewal. The system reads one renewal case and recommends **Renew**, **Renegotiate** or **Switch / Benchmark**, with the evidence behind it.

## 2. Scope

- **In:** one renewal case per run, given as JSON (contract terms, pricing, vendor proposal, SLA, usage, roadmap, history, internal assessment).
- **Out:** an Executive Brief and a Move Trace.
- **Not in scope:** LLMs, external data sources, authentication, sending notices to vendors.

## 3. How it works

```
Case JSON ──► Validate ──► Dossier ──► Moves (in order) ──► Brief + Move Trace ──► Web UI
```

1. **Validate** — the case is checked against a strict schema. Missing or invalid data is rejected (HTTP 422) before any analysis starts.
2. **Dossier** — one shared record of facts. It starts with the validated input and is filled in step by step.
3. **Moves** — run in a fixed order. Each move reads the Dossier, adds its findings, and records what it did.
4. **Output** — the last move makes the decision and assembles the brief.

## 4. Core concepts

| Concept              | Meaning                                                                                                                                                        |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Move**       | One major step of the analysis (e.g. frame goals, check terms, verify deadlines, assess performance, analyze usage, recommend). Each has an ID, name and verb. |
| **Action**     | A unit of logic inside a move. Recorded as **Executed**, **Skipped** (with a reason) or **Failed**.                                          |
| **Gate**       | A decision point inside a move that decides which actions run next. Recorded with its decision and details.                                                    |
| **Dossier**    | The shared fact record. Each move owns its own section.                                                                                                        |
| **Policy**     | The client's renewal rules (`RenewalPolicy`): every threshold a move uses. Versioned in `backend/policies/`; defaults = built-in values (version 0). |
| **Move Trace** | The audit record of every move, action and gate for one run.                                                                                                   |

## 5. Current moves

| ID  | Name                        | Verb     | Contributes                                            |
| --- | --------------------------- | -------- | ------------------------------------------------------ |
| M01 | Set Renewal Goals           | FRAME    | decision question, owner, budget, success criteria     |
| M02 | Check Agreement Terms       | RESEARCH | term, pricing, termination rights, addenda issues      |
| M03 | Check Renewal Deadlines     | VERIFY   | notice cutoff and urgency status                       |
| M04 | Assess Supplier Performance | EVALUATE | uptime, SLA, incidents, credits, performance rating    |
| M05 | Analyze License Needs       | ANALYZE  | utilization, shelfware, seat and module changes        |
| M10 | Model Costs & Recommend     | MODEL    | cost model, risks, decision, strategy, timeline, brief |

## 6. Outputs

**Executive Brief** — decision and rationale, vendor, financials (current vs proposed, budget gap, price cap, 3-year view), seats and usage, performance, risks, strategic options, negotiation objectives, timeline, and notice status.

**Move Trace** — for each move: status, summary, actions (executed/skipped/failed with reasons and timing) and gates (decision and details).

## 7. Design rules

- **Deterministic** — same input and same assessment date always give the same result.
- **No guessing** — required data must be present; nothing is defaulted. Unknown facts stay empty.
- **Explainable** — every branch is a recorded gate; every skipped action states why.
- **Policy-driven** — no decision threshold is written in a move; each comes from the policy, and the brief reports the policy version and the rule checks (`meta.rule_checks`, `meta.decided_by`) that set the label.
- **Ordered** — a move may only use facts produced by moves before it. The recommending move runs last.
- **Date-aware** — results depend on the assessment date, which defaults to today and can be fixed for repeatable runs.
- **Lightweight** — Python + FastAPI backend; plain HTML/CSS/JS frontend with no frameworks or build step.

## 8. Interfaces

| Endpoint                                | Purpose                                    |
| --------------------------------------- | ------------------------------------------ |
| `GET /health`                         | Health check                               |
| `GET /api/cases`                      | List stored cases                          |
| `GET /api/case/{id}?as_of=YYYY-MM-DD` | Run a stored case and return brief + trace |
| `POST /api/process`                   | Run a case sent in the request             |
| `POST /api/upload`                    | Validate and store a new case              |
| `GET /api/policy`                     | Current policy, defaults and field catalog |
| `PUT /api/policy`                     | Save a new policy version (422 if invalid) |
| `GET /api/policy/history`             | Saved policy versions, newest first        |
| `POST /api/policy/preview`            | Run all cases with a draft policy, no save |

The web UI shows the brief, lets the user switch or upload cases, view the Move Flow (trace), and print to PDF.

## 9. Layout

```
backend/app/core/     framework: base move, dossier, orchestrator
backend/app/models/   input schema, renewal policy
backend/app/moves/    one file per move
backend/data/         stored cases
backend/policies/     saved policy versions (runtime data, git-ignored)
backend/tests/        golden, boundary, policy and API tests (pytest)
backend/main.py       API + static hosting
frontend/             UI
sample_uploads/       test cases, named by expected result
```

## 10. Quality

- Every decision path has a sample case in `sample_uploads/` named by its expected result.
- Changes must keep existing samples at their expected results (checked with a fixed assessment date).
- Invalid-input samples must still be rejected with 422.
