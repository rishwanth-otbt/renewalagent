"""Builds M01_Set_Renewal_Goals.html from the reference implementation, scenario runs and eval results.
Run:  python build_page.py   (re-run after changing the .py or .yaml so the page stays in sync)"""
import html
import inspect
import io
import json
import contextlib
from dataclasses import asdict
from pathlib import Path

import m01_set_renewal_goals as m
import test_m01_evals as t

HERE = Path(__file__).parent
E = html.escape


def code(src: str, lang: str) -> str:
    return f'<pre class="code" data-lang="{lang}"><code>{E(src.rstrip())}</code></pre>'


def src(*fns) -> str:
    return "\n\n".join(inspect.getsource(f).rstrip() for f in fns)


# ----------------------------------------------------------------------------- actions content
ACTIONS = [
    {
        "id": "A1", "name": "Load context", "kind": "Code", "effect": "Read-only", "gate": "G0 after",
        "biz": "Collect what the company already knows before asking anyone anything: the request, the account, "
               "the subscription, the list of agreements (MSA, order form, SLA, amendments, quotes) with their "
               "status and version, the mandate, and any earlier brief. It <b>lists</b> documents; it does not read "
               "clauses (that is M02). It also applies the information barrier: a buyer never loads the supplier's "
               "private material, and a supplier never loads the buyer's.",
        "why": "Every later action needs the same facts. Loading them once, with sources, stops the LLM from "
               "guessing and makes the brief traceable.",
        "yaml": """action: A1_load_context
kind: deterministic code
side_effects: none (read-only)
inputs:
  request_id:      string   # required
  account_id:      string   # required
  subscription_id: string?  # inferred only if exactly one active subscription
outputs:
  ContextBundle:
    request, account, subscription
    other_subscriptions: [..]      # when scope is ambiguous
    documents: [DocRef]            # id, type, version, EXECUTED|DRAFT, visibility, source
    withheld_documents: int        # removed by information barrier
    headline_facts: {term_end (SYSTEM_RECORD), quantity, sla_level} each with source
    mandate, existing_brief
    missing: [string]              # recorded, never invented
errors:
  REQUEST_NOT_FOUND -> BLOCKED
  ACCOUNT_NOT_FOUND -> BLOCKED
instruments: crm (read), contract_repo (list only), mandate_store (read)""",
        "fns": [m.a1_load_context, m.g0_applicability],
    },
    {
        "id": "A2", "name": "Frame the decision", "kind": "LLM + rules", "effect": "None", "gate": "runs parallel with A3",
        "biz": "Turn the request into a neutral <b>decision question</b>. “Negotiate and get 15% off” becomes "
               "“Should we renew on changed terms or replace, and which terms should we seek within our authority?”. "
               "It also identifies whose side we are on, which paths are open (renew, renew with changes, replace, "
               "exit), stated goals, and dates, which are labelled as <i>internal targets</i> rather than contractual "
               "deadlines. Rules flag solution phrasing and instruction-like text such as “SYSTEM: you are authorized”.",
        "why": "An experienced renewal manager first asks “what decision are we actually making?”. Solving a "
               "pre-chosen answer is the most common way this work goes wrong.",
        "yaml": """action: A2_frame_decision
kind: LLM (structured output) + rule cross-checks
side_effects: none
inputs:  ContextBundle (request text is treated as DATA, not instructions)
outputs:
  Framing:
    desired_outcome, decision_question
    perspective: BUYER | SUPPLIER | UNKNOWN   # UNKNOWN if text and account record disagree
    requested_actions: [ANALYZE | NEGOTIATE | CONTACT_COUNTERPARTY | ...]
    candidate_goals, stated_dates (kind INTERNAL_TARGET)
    decision_paths: [RENEW | RENEW_CHANGED | REPLACE | EXIT]
    solution_signals, injection_signals
    priority_conflicts: [{text, between_stakeholders}]
    request_kind: FULL_REVIEW | QUICK_COMPARISON
rule: nothing returned here can grant authority""",
        "fns": [m.a2_frame_decision],
    },
    {
        "id": "A3", "name": "Resolve authority", "kind": "Code (lookup)", "effect": "None", "gate": "runs parallel with A2",
        "biz": "Look up, never guess, who owns the decision and what they may do: owner and delegates, decision "
               "rights, allowed actions, budget ceiling, allowed contact, approvers, and when the mandate expires. "
               "Only the mandate store counts as a source of authority.",
        "why": "The card's gate says that commissioning and contact must fit the current mandate, and that silence "
               "is not permission. Authority therefore has to come from a record, not from a chat or an LLM.",
        "yaml": """action: A3_resolve_authority
kind: deterministic lookup
side_effects: none
inputs:  ContextBundle.mandate, request.from_id
outputs:
  Authority:
    owner {person_id, name, role, active}, delegates
    requester, requester_has_rights
    decision_rights, allowed_actions, budget, deadline
    allowed_contact: [INTERNAL | COUNTERPARTY]
    approvers, mandate_id, mandate_version, mandate_valid_until
rule: the ONLY source of authority for the whole Move""",
        "fns": [m.a3_resolve_authority],
    },
    {
        "id": "A4", "name": "Find gaps and conflicts", "kind": "Rules", "effect": "None", "gate": "routes to G1 / A7 / ESCALATED",
        "biz": "Compare what was asked with what is known and allowed, and list every gap with a severity. "
               "<b>BLOCKING</b>: nothing can be published (no owner, expired mandate, unclear side, out-of-mandate "
               "actions, ambiguous subscription, date after term end). <b>MATERIAL</b>: can be published only as "
               "qualified (no budget, renew-or-replace unclear, priority conflict). <b>MINOR</b>: recorded (missing "
               "documents go to M02, requester without rights, injection attempt).",
        "why": "This is the decision point of the graph. Its output decides whether we ask, escalate, or move on to "
               "writing criteria.",
        "yaml": """action: A4_find_gaps
kind: deterministic rules
side_effects: none
inputs:  ContextBundle, Framing, Authority, resolved gap ids, pending mandate items, today
outputs: [Gap {gap_id, kind, severity, description, question?, ask_to?, suggest_move?, answerable}]
routing:
  OWNER gap                         -> ESCALATED (M32)
  askable gaps not yet asked, round<2 -> G1 -> A5
  BLOCKING left, nothing to ask     -> ESCALATED (M32)
  otherwise                         -> A7
note: stakeholder disagreements go to M29 (not asked here)""",
        "fns": [m.a4_find_gaps],
    },
    {
        "id": "A5", "name": "Ask the owner", "kind": "Human-in-the-loop", "effect": "Sends internal message", "gate": "G1 before",
        "biz": "Send at most three pointed questions, blocking ones first, only to the owner or a recorded delegate "
               "on the internal channel, then pause the run. Each question is tied to a gap that could change "
               "the decision.",
        "why": "People's time is the scarce resource. Fewer, sharper questions get answered. Never contact the "
               "supplier or customer from this Move.",
        "yaml": """action: A5_ask_owner
kind: human-in-the-loop
side_effects: sends internal message(s)   # guarded by G1
inputs:  gaps that passed G1 (max 3 per round), round number
outputs: {round, sent: [{to, message_ref}], recipients, questions}
then:    state AWAITING_OWNER (events: owner_reply | owner_timeout)
limits:  2 rounds; a gap is never asked twice""",
        "fns": [m.g1_contact_gate, m.a5_ask_owner],
    },
    {
        "id": "A6", "name": "Record answers", "kind": "LLM parse + code", "effect": "None", "gate": "back to A4",
        "biz": "Turn the owner's free-text reply into attributed answers (who said what, in which message). "
               "<b>Code</b> decides what may change. A reply may <i>narrow</i> scope (“analysis only”) but never "
               "<i>widen</i> authority (“yes, negotiate”). A widening request is recorded as a <b>pending mandate "
               "update</b>, and any attempt to change other fields is rejected.",
        "why": "The owner's word in a chat is evidence, not a mandate. Keeping that line strict is what makes the "
               "agent safe to run.",
        "yaml": """action: A6_record_answers
kind: LLM parsing + code validation
side_effects: none
inputs:  outstanding questions, reply text, sender (must be someone who was asked), message ref
outputs:
  answers: [Answer {gap_id, text, answered_by, message_ref, resolves}]
  applied_updates      # only: requested_actions (narrowing), decision_paths,
                       #       priority_conflicts, perspective (if UNKNOWN)
  pending_mandate      # actions the owner wants but the mandate lacks
  rejected_updates     # anything else, e.g. decision_question
rule: answers to non-answerable gaps (expired mandate, no owner) never resolve them""",
        "fns": [m.a6_record_answers],
    },
    {
        "id": "A7", "name": "Set success criteria and exclusions", "kind": "LLM draft", "effect": "None", "gate": "",
        "biz": "Write what “good” looks like as measurable <b>MUST</b> and <b>SHOULD</b> criteria, each with "
               "its source and the later Move that will provide the evidence (for example “annual cost below "
               "$130,000” needs M02 and M10). Code then adds an exclusion for every requested action the mandate "
               "doesn't allow.",
        "why": "Later Moves (M18 Summarize, M19 Recommend) judge options against these criteria. Without them, "
               "“best option” has no meaning.",
        "yaml": """action: A7_set_success_criteria
kind: LLM draft (+ code-added exclusions)
side_effects: none
inputs:  Framing, Answers, Authority, pending mandate items
outputs:
  criteria: [Criterion {id, statement, priority MUST|SHOULD, measure, target, source, depends_on}]
  exclusions: [string]   # every unauthorized action appears here""",
        "fns": [m.a7_set_success_criteria],
    },
    {
        "id": "A8", "name": "Assemble brief", "kind": "Code", "effect": "None", "gate": "",
        "biz": "Put everything into the Review brief schema: question, side, paths, mode (FULL or LIGHT), "
               "accountable owner versus preparer, authorized actions, exclusions, budget, labelled dates, "
               "criteria, evidence list, open questions, unresolved authority, and recommended next Moves. "
               "It creates no new facts.",
        "why": "A fixed schema lets other Moves and the Dossier read the brief without interpretation.",
        "yaml": """action: A8_assemble_brief
kind: deterministic code
side_effects: none
inputs:  ContextBundle, Framing, Authority, criteria, exclusions, gaps, version
outputs: ReviewBrief (see contract)
rule: recommended_next_moves are advisory; the Manager commissions work""",
        "fns": [m.a8_assemble_brief, m.recommend_next_moves],
    },
    {
        "id": "A9", "name": "Validate brief", "kind": "Code (checks)", "effect": "None", "gate": "G2 after",
        "biz": "Run checks C1–C7. If a fixable check fails, the run goes back to the action that caused it "
               "(C1 to A2, C4 to A7) at most twice. Any other failure is a defect and stops the run.",
        "why": "These are the card's quality controls turned into tests the agent runs on itself.",
        "yaml": """action: A9_validate_brief
kind: deterministic checks
side_effects: none
inputs:  ReviewBrief, Authority, Framing, known source refs
outputs: [failure codes]   # empty = pass
routing: C1 -> A2 | C4 -> A7 | others -> BLOCKED | pass -> G2""",
        "fns": [m.a9_validate_brief, m.g2_authority_gate],
    },
    {
        "id": "A10", "name": "Publish brief", "kind": "Code", "effect": "Writes Dossier, notifies requester", "gate": "G3 before",
        "biz": "Publish only after the owner or a delegate has confirmed <b>this exact version</b> and the mandate "
               "hasn't changed since framing. If someone else made the request, tell them how it was scoped.",
        "why": "Publication is what lets other Moves start, so it is the final controlled step.",
        "yaml": """action: A10_publish
kind: code
side_effects: writes Dossier section 'decision_question_and_mandate'; internal notification (G1)
inputs:  confirmed ReviewBrief
outputs: dossier_ref
end states: COMPLETE (authoritative) | QUALIFIED_COMPLETE""",
        "fns": [m.a10_publish],
    },
]

GATES = [
    ("G0", "Applicability", "After A1",
     "Reuse the existing brief only when it is for the <b>same request</b>, under the <b>same mandate version</b>, and already confirmed. With no mandate, never reuse.",
     "REUSED, or continue to A2 ∥ A3"),
    ("G1", "Contact", "Before every outgoing message",
     "Internal contact must be allowed by the mandate. Questions and confirmations go only to the owner or a recorded delegate; notifications go only to the requester. M01 never contacts the counterparty.",
     "Message refused and logged"),
    ("G2", "Authority level", "After A9",
     "If any MATERIAL gap or unresolved authority remains, the brief can only be published as QUALIFIED. BLOCKING gaps never reach this gate.",
     "QUALIFIED instead of AUTHORITATIVE"),
    ("G3", "Confirmation", "Before A10",
     "The sender must be the owner or a delegate, confirming this exact version, and the mandate version must be unchanged since framing.",
     "Refused (state unchanged) or reframe from A1"),
]

CHECKS = [
    ("C1", "Decision question is a question and states no committed solution", "A2 (repair)"),
    ("C2", "Accountable owner present and distinct from the preparer (agent)", "Defect → BLOCKED"),
    ("C3", "Required fields present (question, side, account, request)", "Defect → BLOCKED"),
    ("C4", "FULL mode has a MUST criterion; all criteria measurable; no two MUSTs on the same measure", "A7 (repair)"),
    ("C5", "Authorized actions are within the mandate; every unauthorized request is listed as an exclusion", "Defect → BLOCKED"),
    ("C6", "Every date has a kind and a source; CONTRACTUAL only with a contract source", "Defect → BLOCKED"),
    ("C7", "Every criterion cites a known source; budget comes from the mandate store", "Defect → BLOCKED"),
]

GAP_RULES = [
    ("No mandate / no active owner", "BLOCKING", "ESCALATED → M32"),
    ("Mandate expired", "BLOCKING", "Ask owner to renew it in the mandate store; a chat answer cannot resolve it"),
    ("Several subscriptions, none specified", "BLOCKING", "Ask which subscription(s), and whether to co-term"),
    ("Buyer/supplier side unclear", "BLOCKING", "Ask"),
    ("Requested actions outside mandate", "BLOCKING", "Ask whether to stay within the mandate"),
    ("Requested date after term end", "BLOCKING", "Ask; M03 suggested"),
    ("Owner wants more authority than the mandate gives", "MATERIAL", "Pending mandate update → M33"),
    ("No budget ceiling", "MATERIAL", "Ask; M32 chases the budget owner"),
    ("Renew-or-replace unclear", "MATERIAL", "Ask"),
    ("Priority conflict in one instruction", "MATERIAL", "Ask the owner"),
    ("Priority conflict between stakeholders", "MATERIAL", "Not settled here → M29"),
    ("Requester has no decision right", "MINOR", "Record; inform requester after publishing"),
    ("Instruction-like text in request", "MINOR", "Flag; take no authority from it"),
    ("Missing executed documents", "MINOR", "Pass to M02"),
]

METHODS = [
    ("Gather context", "Deterministic code", "LLM search over documents", "Facts must be exact and sourced; reading clauses belongs to M02."),
    ("Interpret the request", "LLM (structured) + rules", "Rules only (too brittle); human only (too slow)", "Free text needs language understanding; rules catch solution phrasing and injection the LLM might miss."),
    ("Who may decide what", "Deterministic lookup", "LLM inference from emails", "Authority must never be inferred. An LLM guess here is the most dangerous failure."),
    ("Find gaps", "Expert rules", "LLM judgement; probabilistic scoring", "Gaps must be explainable and reproducible. Severity drives what may be published."),
    ("Resolve ambiguity", "Human judgement (owner)", "LLM picks the most likely meaning", "Only the accountable owner can settle scope and priorities. Silence is not permission."),
    ("Parse the owner's reply", "LLM + code whitelist", "Code only", "Replies are free text; code limits what a reply may change."),
    ("Write success criteria", "LLM draft + owner confirmation", "Fixed template", "Goals differ per renewal, so the owner confirms the final wording."),
    ("Assemble and check", "Deterministic code", "LLM self-review", "Schema and checks must be identical every run."),
]

FAILURES = [
    ("Solving the wrong problem", "Treating “get 15% off” as the goal, instead of deciding whether and how to renew."),
    ("Acting without authority", "Starting negotiation or contacting the supplier when only analysis was approved."),
    ("Silence as permission", "Proceeding because the owner didn't object."),
    ("Wrong owner", "Taking instructions from the loudest requester instead of the accountable owner."),
    ("Invented facts", "Guessing a budget, deadline or SLA level that is not on record."),
    ("Target vs deadline", "Treating “decide by 31 March” as a contractual deadline."),
    ("Unmeasurable goals", "“Get a good deal”: later Moves can't judge options against it."),
    ("Scope creep", "Turning a quick comparison into a full renewal programme."),
]

USES = [
    ("V01 Frame", "Pre-analysis step of the Frame play (with M13). The brief is the Dossier's “decision question, scope and success criteria”."),
    ("V03 Consult / V11 Plan", "Clarifies the mandate before stakeholders are consulted, and sets the scope that the plan's priorities and owners follow."),
    ("Any other Verb (Optimize, Negotiate, Compare …)", "The Manager runs M01 first when no valid brief exists for the request. Example: “Optimize our renewal” → M01 scopes the work → M05, M10, M11 run inside that scope."),
    ("Re-entry", "When the mandate changes (new owner, budget, authority, expiry) or M33 reports a change that invalidates the brief."),
    ("Supplier side", "A supplier's account team frames its opening proposal (the card's Westbrook case). The barrier withholds the buyer's private material."),
    ("Quick comparison", "LIGHT mode: no MUST criterion, no budget question, no deadline Move. It stays a quick comparison."),
]

POLICY = [
    ("Who may confirm a brief?", "Owner or a recorded delegate.", "Open"),
    ("Is an owner's chat reply a mandate change?", "No. Only an update to the mandate store changes authority.", "Proposed"),
    ("When is an old brief reusable?", "Same request, same mandate version, already confirmed.", "Proposed"),
    ("Budget missing: may analysis proceed?", "Yes, as a QUALIFIED brief; M32 chases the budget owner.", "Open"),
    ("Does a quick comparison need owner confirmation?", "Yes (current code). Could be relaxed.", "Open"),
    ("Clarification and confirmation timeouts", "Not set. Suggested: 3 and 5 business days.", "Open"),
    ("Bundles of subscriptions: one brief or several?", "One brief per subscription for now.", "Open"),
    ("Information barrier tags on documents", "Requires a visibility field (SHARED / BUYER_PRIVATE / SUPPLIER_PRIVATE) in the repository.", "Integration"),
    ("LLM prompts and model", "Scripted stand-in today; prompts must be written and evaluated against the same evals.", "Integration"),
    ("Mandate store, CRM, contract repository APIs", "Interfaces defined (ports); real adapters not built.", "Integration"),
]


# ----------------------------------------------------------------------------- runs
def run_capture(fn):
    run, msg, dos = fn()
    return run, msg, dos


def eval_results():
    rows = []
    for cat, case, expected, fn in t.EVALS:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                fn()
            ok = True
        except Exception:
            ok = False
        rows.append((cat, case, expected, ok))
    return rows


def brief_view(b) -> dict:
    d = asdict(b)
    return {
        "status": d["status"], "confirmed_by": d["confirmed_by"], "perspective": d["perspective"],
        "decision_question": d["decision_question"], "decision_paths": d["decision_paths"], "mode": d["mode"],
        "accountable": d["responsibility"]["accountable"]["name"],
        "authorized_actions": d["authorized_actions"], "exclusions": d["exclusions"],
        "budget": d["budget"] and f'{d["budget"]["amount"]:,} {d["budget"]["currency"]} ({d["budget"]["source"]["ref"]})',
        "dates": [f'{x["kind"]}: {x["label"]} = {x["date"]}' for x in d["dates"]],
        "success_criteria": [f'{c["priority"]} {c["criterion_id"]}: {c["statement"]} [{c["target"]}] '
                             f'(source {c["source"]["ref"]}; evidence from {", ".join(c["depends_on"])})'
                             for c in d["success_criteria"]],
        "evidence_inventory": [f'{x["doc_id"]} {x["doc_type"]} {x["status"]}' for x in d["evidence_inventory"]],
        "open_questions": [f'{q["severity"]}: {q["description"]}' for q in d["open_questions"]],
        "unresolved_authority": d["unresolved_authority"],
        "recommended_next_moves": [f'{x["move"]}: {x["why"]}' for x in d["recommended_next_moves"]],
    }


def trace_rows(run) -> str:
    out = []
    for line in run.trace:
        if "->" in line[:50]:
            frm, rest = line.split("->", 1)
            to, note = rest.strip()[:22].strip(), rest.strip()[22:].strip()
            out.append(f"<tr><td><span class='st'>{E(frm.strip())}</span></td><td><span class='st'>{E(to)}</span></td>"
                       f"<td>{E(note)}</td></tr>")
        else:
            out.append(f"<tr class='note'><td></td><td></td><td>↳ {E(line.strip())}</td></tr>")
    return "<div class='scroll'><table class='trace'><thead><tr><th>From</th><th>To</th><th>What happened</th></tr></thead><tbody>" + "".join(out) + "</tbody></table></div>"


def messages(msg) -> str:
    return "".join(f"<div class='msg'><div class='msg-h'><span>to <b>{E(x['to'])}</b> · {E(x['channel'])}</span>"
                   f"<span>{E(x['subject'])}</span></div><pre>{E(x['body'])}</pre></div>" for x in msg.outbox)


# ----------------------------------------------------------------------------- page
MAP = """flowchart TD
  S(["Start: request_id, account_id, subscription_id?"]) --> A1["A1 Load context<br/>code · read-only"]
  A1 -->|"not found"| BL(["BLOCKED"])
  A1 --> G0{"G0 Same request<br/>and mandate version?"}
  G0 -->|"yes"| RU(["REUSED"])
  G0 -->|"no"| A2["A2 Frame the decision<br/>LLM + rules"]
  G0 -->|"no"| A3["A3 Resolve authority<br/>code lookup"]
  A2 --> J(("join"))
  A3 --> J
  J --> A4["A4 Find gaps and conflicts<br/>rules"]
  A4 -->|"no owner or mandate"| ES(["ESCALATED → M32"])
  A4 -->|"askable gaps, round < 2"| G1{"G1 Contact allowed?"}
  G1 -->|"yes"| A5["A5 Ask the owner<br/>human-in-the-loop"]
  A5 -.->|"pause"| W[["AWAITING_OWNER"]]
  W -->|"owner_reply"| A6["A6 Record answers<br/>LLM parse + code"]
  W -->|"owner_timeout"| A4
  A6 --> A4
  A4 -->|"BLOCKING left, nothing to ask"| ES
  A4 -->|"no BLOCKING gaps"| A7["A7 Set success criteria<br/>LLM draft"]
  A7 --> A8["A8 Assemble brief<br/>code"]
  A8 --> A9["A9 Validate C1–C7<br/>code"]
  A9 -->|"C1 fails"| A2
  A9 -->|"C4 fails"| A7
  A9 -->|"other failure"| BL
  A9 -->|"pass"| G2{"G2 Authority level<br/>AUTHORITATIVE or QUALIFIED"}
  G2 --> G3{"G3 Owner confirms<br/>this version?"}
  G3 -->|"change request"| A7
  G3 -->|"timeout"| ES
  G3 -->|"confirmed"| A10["A10 Publish to Dossier<br/>notify requester"]
  A10 --> DONE(["COMPLETE or QUALIFIED_COMPLETE"])
  ES -.->|"owner_assigned / mandate_changed"| A1"""

STATES = """stateDiagram-v2
  [*] --> LOADING_CONTEXT
  LOADING_CONTEXT --> REUSED: G0 reuse
  LOADING_CONTEXT --> BLOCKED: not found
  LOADING_CONTEXT --> FRAMING
  FRAMING --> ASSESSING: A2 and A3 joined
  ASSESSING --> AWAITING_OWNER: G1 ok, A5 sent
  AWAITING_OWNER --> ASSESSING: reply (A6) or timeout
  ASSESSING --> ESCALATED: no owner, or BLOCKING left
  ASSESSING --> DRAFTING_CRITERIA: no BLOCKING gaps
  DRAFTING_CRITERIA --> ASSEMBLING
  ASSEMBLING --> VALIDATING
  VALIDATING --> FRAMING: C1 repair
  VALIDATING --> DRAFTING_CRITERIA: C4 repair
  VALIDATING --> BLOCKED: defect
  VALIDATING --> AWAITING_CONFIRMATION: G2, G1, G3 request
  AWAITING_CONFIRMATION --> COMPLETE: G3 confirmed
  AWAITING_CONFIRMATION --> QUALIFIED_COMPLETE: G3 confirmed (qualified)
  AWAITING_CONFIRMATION --> DRAFTING_CRITERIA: change request
  AWAITING_CONFIRMATION --> ESCALATED: timeout
  ESCALATED --> LOADING_CONTEXT: owner_assigned / mandate_changed
  COMPLETE --> [*]
  QUALIFIED_COMPLETE --> [*]
  REUSED --> [*]
  BLOCKED --> [*]"""

ORDER = [
    ("1", "A1", "Sequential", "Load context. If the request or account is missing → BLOCKED. Then G0: is this the same request under the same mandate version? Yes → REUSED."),
    ("2", "A2 ∥ A3", "Parallel", "Framing (LLM) and authority lookup (code) don't depend on each other, so they run at the same time and join before A4."),
    ("3", "A4", "Decision point", "Rules list gaps. No owner → ESCALATED. Questions to ask → step 4. Blocking gaps but nothing left to ask → ESCALATED. Otherwise → step 6."),
    ("4", "G1 → A5", "Gate, then pause", "Each question passes the contact gate. At most 3 questions per round, at most 2 rounds. The run pauses in AWAITING_OWNER."),
    ("5", "A6 → A4", "Loop", "The reply is recorded and validated, then A4 runs again with the answers. A timeout also returns to A4, but resolves nothing."),
    ("6", "A7 → A8 → A9", "Sequential", "Draft criteria, assemble the brief, run checks. C1 failure → back to A2; C4 failure → back to A7 (max 2 repairs)."),
    ("7", "G2 → G1 → G3", "Gates, then pause", "Decide AUTHORITATIVE or QUALIFIED, send the confirmation request (contact gate), and pause in AWAITING_CONFIRMATION."),
    ("8", "A10", "Final", "On a valid confirmation: publish, notify the requester if different, and end in COMPLETE or QUALIFIED_COMPLETE."),
]

EVENTS = [
    ("owner_reply", "AWAITING_OWNER", "A6 (only if the sender was asked)"),
    ("owner_timeout", "AWAITING_OWNER", "A4 again. Gaps stay open."),
    ("owner_confirm", "AWAITING_CONFIRMATION", "G3 checks sender, version and mandate → A10"),
    ("owner_change_request", "AWAITING_CONFIRMATION", "A8 (question rewrite) or A7 (criteria)"),
    ("confirmation_timeout", "AWAITING_CONFIRMATION", "ESCALATED. Nothing published."),
    ("owner_assigned", "ESCALATED", "Restart from A1"),
    ("mandate_changed", "any waiting state", "Restart from A1. Answers kept as history."),
    ("cancel", "any non-final state", "CANCELLED"),
]


def build():
    ra, msa, _ = run_capture(m.run_scenario_a)
    rb, msb, _ = run_capture(m.run_scenario_b)
    evals = eval_results()
    passed = sum(1 for r in evals if r[3])
    a_req = m.scenario_a()[1]["requests"]["REQ-101"]
    b_req = m.scenario_b()[1]["requests"]["REQ-202"]

    action_cards = []
    for a in ACTIONS:
        action_cards.append(f"""
<article class="action" id="{a['id'].lower()}">
  <header class="action-h">
    <span class="aid">{a['id']}</span>
    <h3>{E(a['name'])}</h3>
    <div class="tags"><span class="tag k">{E(a['kind'])}</span><span class="tag e">{E(a['effect'])}</span>{f"<span class='tag g'>{E(a['gate'])}</span>" if a['gate'] else ""}</div>
  </header>
  <div class="biz">
    <div><h4>What it does (business)</h4><p>{a['biz']}</p></div>
    <div><h4>Why it matters</h4><p>{a['why']}</p></div>
  </div>
  <div class="codes">
    <div class="codecol"><h4>Action contract · YAML</h4>{code(a['yaml'], 'yaml')}</div>
    <details class="codecol"><summary>Python · executable function</summary>{code(src(*a['fns']), 'python')}</details>
  </div>
</article>""")

    gates_html = "".join(f"<tr><td><span class='gid'>{g}</span></td><td><b>{n}</b></td><td>{p}</td><td>{r}</td><td>{f}</td></tr>"
                         for g, n, p, r, f in GATES)
    checks_html = "".join(f"<tr><td><span class='cid'>{c}</span></td><td>{E(d)}</td><td>{E(f)}</td></tr>" for c, d, f in CHECKS)
    gaprules_html = "".join(f"<tr><td>{E(a)}</td><td><span class='sev {s.lower()}'>{s}</span></td><td>{E(r)}</td></tr>"
                            for a, s, r in GAP_RULES)
    methods_html = "".join(f"<tr><td><b>{E(a)}</b></td><td>{E(b)}</td><td class='muted'>{E(c)}</td><td>{E(d)}</td></tr>"
                           for a, b, c, d in METHODS)
    fail_html = "".join(f"<li><b>{E(a)}.</b> {E(b)}</li>" for a, b in FAILURES)
    uses_html = "".join(f"<div class='use'><h4>{E(a)}</h4><p>{E(b)}</p></div>" for a, b in USES)
    order_html = "".join(f"<tr><td class='num'>{n}</td><td><b>{E(a)}</b></td><td><span class='mode'>{E(k)}</span></td><td>{E(d)}</td></tr>"
                         for n, a, k, d in ORDER)
    events_html = "".join(f"<tr><td><code>{E(a)}</code></td><td>{E(b)}</td><td>{E(c)}</td></tr>" for a, b, c in EVENTS)
    evals_html = "".join(f"<tr><td class='num'>E{i:02d}</td><td><span class='cat'>{E(c)}</span></td><td>{E(cs)}</td><td>{E(ex)}</td>"
                         f"<td>{'<span class=pass>PASS</span>' if ok else '<span class=fail>FAIL</span>'}</td></tr>"
                         for i, (c, cs, ex, ok) in enumerate(evals, 1))
    policy_html = "".join(f"<tr><td><b>{E(q)}</b></td><td>{E(d)}</td><td><span class='pol {s.lower()}'>{s}</span></td></tr>"
                          for q, d, s in POLICY)
    yaml_full = (HERE / "m01_move.yaml").read_text(encoding="utf-8")

    page = f"""<title>M01 Set Renewal Goals</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=Space+Grotesk:wght@500;600;700&display=swap">
<style>
/* Layout: one reading column (max 1120px) with a contents rail; actions as full-width spec cards. */
:root {{
  --bg: #f6f7f9; --surface: #ffffff; --ink: #18202b; --muted: #5b6676; --line: #dde2ea;
  --accent: #0f6e78; --accent-soft: #e2f1f2;
  --gate: #a35a00; --gate-soft: #fdf0dc; --check: #2c7a3f; --check-soft: #e3f3e6;
  --block: #b3261e; --block-soft: #fbe5e3; --wait: #5a49a8; --wait-soft: #ece9fa;
  --code-bg: #f0f2f6;
  --f-display: "Space Grotesk", "Segoe UI", system-ui, sans-serif;
  --f-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, "Cascadia Code", Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #11161d; --surface: #182029; --ink: #e6ebf1; --muted: #9aa6b5; --line: #2a3542;
  --accent: #5cc2cc; --accent-soft: #15343a;
  --gate: #f0a64a; --gate-soft: #3a2a14; --check: #6fcf86; --check-soft: #173323;
  --block: #ff8a80; --block-soft: #3d1c1a; --wait: #a99cf0; --wait-soft: #262046;
  --code-bg: #0f141a; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #11161d; --surface: #182029; --ink: #e6ebf1; --muted: #9aa6b5; --line: #2a3542;
  --accent: #5cc2cc; --accent-soft: #15343a;
  --gate: #f0a64a; --gate-soft: #3a2a14; --check: #6fcf86; --check-soft: #173323;
  --block: #ff8a80; --block-soft: #3d1c1a; --wait: #a99cf0; --wait-soft: #262046;
  --code-bg: #0f141a; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--ink); font: 15px/1.6 var(--f-body);
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px)); }}
.wrap {{ max-width: 1120px; margin: 0 auto; padding-block: 40px 80px; display: grid; gap: 56px; }}
h1, h2, h3, h4 {{ font-family: var(--f-display); text-wrap: balance; margin: 0; letter-spacing: -0.01em; }}
h1 {{ font-size: clamp(30px, 5vw, 44px); line-height: 1.1; }}
h2 {{ font-size: 26px; line-height: 1.2; }}
h3 {{ font-size: 19px; }}
h4 {{ font-size: 13px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); font-weight: 600; margin-bottom: 6px; }}
p {{ margin: 0; max-width: 72ch; }}
a {{ color: var(--accent); }}
code, .num, .st, .gid, .cid, .aid {{ font-family: var(--f-mono); font-variant-numeric: tabular-nums; }}
.eyebrow {{ font: 500 12px var(--f-mono); letter-spacing: 0.08em; text-transform: uppercase; color: var(--accent); }}
section {{ display: grid; gap: 20px; }}
.sec-h {{ display: grid; gap: 8px; border-top: 2px solid var(--ink); padding-top: 14px; }}
.sec-h p {{ color: var(--muted); }}
.muted {{ color: var(--muted); }}

/* hero */
.hero {{ display: grid; gap: 18px; }}
.hero .lede {{ font-size: 18px; max-width: 64ch; }}
.facts {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1px; background: var(--line);
  border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
.facts div {{ background: var(--surface); padding: 12px 14px; display: grid; gap: 2px; min-width: 0; }}
.facts span {{ font: 500 11px var(--f-mono); text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted); }}
.facts b {{ font-weight: 600; }}
.status {{ display: flex; flex-wrap: wrap; gap: 8px; }}
.pill {{ font: 500 12px var(--f-mono); padding: 4px 10px; border-radius: 99px; border: 1px solid var(--line); background: var(--surface); }}
.pill.ok {{ background: var(--check-soft); color: var(--check); border-color: transparent; }}
.pill.warn {{ background: var(--gate-soft); color: var(--gate); border-color: transparent; }}
nav.toc {{ display: flex; flex-wrap: wrap; gap: 6px; }}
nav.toc a {{ font: 500 13px var(--f-body); text-decoration: none; color: var(--ink); padding: 6px 12px; border: 1px solid var(--line);
  border-radius: 6px; background: var(--surface); }}
nav.toc a:hover, nav.toc a:focus-visible {{ border-color: var(--accent); color: var(--accent); outline: none; }}
nav.toc a b {{ font-family: var(--f-mono); color: var(--accent); margin-right: 4px; }}

/* panels & tables */
.panel {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 20px; display: grid; gap: 12px; min-width: 0; }}
.grid2 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }}
.grid3 {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }}
.scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--surface); }}
table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
th {{ text-align: left; font: 600 12px var(--f-body); text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted);
  padding: 10px 12px; border-bottom: 1px solid var(--line); background: var(--surface); white-space: nowrap; }}
td {{ padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }}
tr:last-child td {{ border-bottom: 0; }}
td.num {{ color: var(--muted); white-space: nowrap; }}
ul.clean {{ margin: 0; padding-left: 18px; display: grid; gap: 6px; }}
.gid {{ background: var(--gate-soft); color: var(--gate); padding: 2px 8px; border-radius: 4px; font-weight: 500; white-space: nowrap; }}
.cid {{ background: var(--check-soft); color: var(--check); padding: 2px 8px; border-radius: 4px; font-weight: 500; }}
.sev {{ font: 500 11px var(--f-mono); padding: 2px 8px; border-radius: 4px; white-space: nowrap; }}
.sev.blocking {{ background: var(--block-soft); color: var(--block); }}
.sev.material {{ background: var(--gate-soft); color: var(--gate); }}
.sev.minor {{ background: var(--code-bg); color: var(--muted); }}
.mode {{ font: 500 12px var(--f-mono); color: var(--wait); white-space: nowrap; }}
.cat {{ font: 500 11px var(--f-mono); color: var(--accent); white-space: nowrap; }}
.pass {{ font: 600 12px var(--f-mono); color: var(--check); }}
.fail {{ font: 600 12px var(--f-mono); color: var(--block); }}
.pol {{ font: 500 11px var(--f-mono); padding: 2px 8px; border-radius: 4px; white-space: nowrap; }}
.pol.open {{ background: var(--gate-soft); color: var(--gate); }}
.pol.proposed {{ background: var(--accent-soft); color: var(--accent); }}
.pol.integration {{ background: var(--wait-soft); color: var(--wait); }}

/* diagrams */
.diagram {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 16px; overflow-x: auto; }}
.diagram pre.mermaid {{ margin: 0; background: transparent; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 14px; font-size: 13px; color: var(--muted); }}
.legend b {{ color: var(--ink); font-family: var(--f-mono); font-weight: 500; }}

/* actions */
.action {{ background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 20px; display: grid; gap: 16px; min-width: 0; }}
.action-h {{ display: flex; flex-wrap: wrap; align-items: center; gap: 10px 14px; }}
.aid {{ font-size: 14px; font-weight: 500; background: var(--ink); color: var(--surface); padding: 3px 9px; border-radius: 5px; }}
.tags {{ display: flex; flex-wrap: wrap; gap: 6px; margin-left: auto; }}
.tag {{ font: 500 11px var(--f-mono); padding: 3px 8px; border-radius: 4px; white-space: nowrap; }}
.tag.k {{ background: var(--accent-soft); color: var(--accent); }}
.tag.e {{ background: var(--code-bg); color: var(--muted); }}
.tag.g {{ background: var(--gate-soft); color: var(--gate); }}
.biz {{ display: grid; grid-template-columns: 3fr 2fr; gap: 20px; }}
.codes {{ display: grid; gap: 12px; }}
.codecol {{ min-width: 0; }}
details.codecol summary {{ cursor: pointer; font: 600 13px var(--f-body); color: var(--accent); padding: 6px 0; }}
details.codecol summary:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
pre.code {{ margin: 0; background: var(--code-bg); border: 1px solid var(--line); border-radius: 6px; padding: 14px; overflow-x: auto;
  font: 12.5px/1.55 var(--f-mono); color: var(--ink); max-height: 560px; }}

/* scenarios */
.scenario {{ display: grid; gap: 16px; }}
.req {{ border-left: 3px solid var(--accent); background: var(--surface); padding: 14px 16px; border-radius: 0 8px 8px 0; font-style: italic; }}
.req span {{ display: block; font: 500 12px var(--f-mono); font-style: normal; color: var(--muted); margin-bottom: 4px; }}
table.trace td {{ font-size: 13px; }}
.st {{ font-size: 12px; background: var(--wait-soft); color: var(--wait); padding: 1px 6px; border-radius: 4px; white-space: nowrap; }}
tr.note td {{ color: var(--gate); font-size: 13px; }}
.msg {{ border: 1px solid var(--line); border-radius: 8px; overflow: hidden; background: var(--surface); }}
.msg-h {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 6px; padding: 8px 12px; background: var(--code-bg); font-size: 13px; }}
.msg pre {{ margin: 0; padding: 12px; white-space: pre-wrap; font: 13px/1.5 var(--f-mono); }}
.shows {{ background: var(--accent-soft); border-radius: 8px; padding: 14px 16px; }}
.shows ul {{ margin: 6px 0 0; padding-left: 18px; display: grid; gap: 4px; }}
.use {{ background: var(--surface); border: 1px solid var(--line); border-radius: 8px; padding: 16px; display: grid; gap: 6px; }}
.use h4 {{ color: var(--accent); }}
.verdict {{ display: grid; grid-template-columns: auto 1fr; gap: 16px; align-items: start; background: var(--surface);
  border: 1px solid var(--line); border-left: 4px solid var(--gate); border-radius: 8px; padding: 18px 20px; }}
.verdict .big {{ font: 700 15px var(--f-display); color: var(--gate); text-transform: uppercase; letter-spacing: 0.04em; }}
footer {{ color: var(--muted); font-size: 13px; border-top: 1px solid var(--line); padding-top: 16px; display: grid; gap: 6px; }}
@media (max-width: 720px) {{
  .biz {{ grid-template-columns: 1fr; }}
  .tags {{ margin-left: 0; }}
  .verdict {{ grid-template-columns: 1fr; }}
  .wrap {{ gap: 44px; padding-block: 24px 60px; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior: auto !important; }} }}
html {{ scroll-behavior: smooth; }}
</style>

<main class="wrap">

<header class="hero">
  <div class="eyebrow">Kozmo Renewal Desk · Move card M01 · design v0.2.1</div>
  <h1>M01 Set Renewal Goals</h1>
  <p class="lede">Before any analysis starts, agree <b>which decision</b> the Review must support, <b>who owns it</b>, and <b>what work is authorized</b>. The output is a bounded Review brief that every later Move works inside.</p>
  <div class="facts">
    <div><span>Verb routes</span><b>Frame · Consult · Plan</b></div>
    <div><span>Position in play</span><b>PRE (pre-analysis)</b></div>
    <div><span>Owner</span><b>Accountable renewal owner</b></div>
    <div><span>Dossier section</span><b>Decision question + mandate</b></div>
    <div><span>Shape</span><b>10 actions · 4 gates · 7 checks</b></div>
  </div>
  <div class="status">
    <span class="pill ok">{passed}/{len(evals)} evals pass</span>
    <span class="pill ok">2 scenarios executed</span>
    <span class="pill warn">Not released: prototype-ready, not production-ready</span>
  </div>
  <nav class="toc" aria-label="Contents">
    <a href="#problem"><b>0</b>Business problem</a>
    <a href="#map"><b>1</b>Map</a>
    <a href="#order"><b>2</b>Execution order</a>
    <a href="#actions"><b>3</b>Actions</a>
    <a href="#scenarios"><b>4</b>Scenarios and usage</a>
    <a href="#contract"><b>5</b>Move contract</a>
    <a href="#gates"><b>6</b>Gates and checks</a>
    <a href="#evals"><b>7</b>Evals</a>
    <a href="#readiness"><b>8</b>Readiness</a>
  </nav>
</header>

<section id="problem">
  <div class="sec-h"><div class="eyebrow">Step 1 + 2 · Business problem and method selection</div><h2>Why this Move exists</h2>
  <p>An experienced renewal manager never starts by comparing prices. First they pin down the actual question, whose decision it is, what they are allowed to do, and what a good result looks like.</p></div>
  <div class="grid2">
    <div class="panel"><h4>What the practitioner is trying to achieve</h4>
      <p>Turn a vague or solution-phrased request (“get us 15% off”) into a neutral decision question with an accountable owner, scope, budget, deadline, allowed contact, measurable success criteria and explicit exclusions. Missing or contradictory authority is written down, never assumed.</p>
      <h4 style="margin-top:8px">When it is useful</h4>
      <p>A new renewal request, a changed mandate, an unclear purpose, or a change reported by M33. A quick comparison gets a LIGHT brief instead of becoming a full programme.</p>
      <h4 style="margin-top:8px">What makes the result valuable</h4>
      <p>Later Moves don't waste effort on the wrong question, nobody acts beyond their authority, and M18/M19 have criteria to judge options against.</p>
    </div>
    <div class="panel"><h4>What makes it fail</h4><ul class="clean">{fail_html}</ul></div>
  </div>
  <div class="panel"><h4>Competency definition</h4>
    <p>Given a renewal request and the account context, M01 produces a <b>Review brief</b> that (1) states a decision question, not a solution; (2) names the accountable owner and keeps them distinct from whoever prepares the work; (3) authorizes only what the mandate allows and lists everything else as an exclusion; (4) gives measurable, sourced MUST/SHOULD criteria; (5) labels every date as contractual, system record or internal target; and (6) records every unresolved authority question with a next step.</p>
  </div>
  <div class="scroll"><table>
    <thead><tr><th>Sub-problem</th><th>Chosen method</th><th>Rejected alternative</th><th>Why</th></tr></thead>
    <tbody>{methods_html}</tbody></table></div>
</section>

<section id="map">
  <div class="sec-h"><div class="eyebrow">Section 1 · Map</div><h2>The Move as a graph</h2>
  <p>Nodes are actions. Diamonds are gates or decisions. Dashed arrows are pauses and resumes. A2 and A3 run in parallel and join before A4. A4 → A5 → A6 → A4 is the clarification loop.</p></div>
  <div class="diagram"><pre class="mermaid">{E(MAP)}</pre></div>
  <div class="legend"><span><b>[ ]</b> action</span><span><b>{{ }}</b> gate / condition</span><span><b>[[ ]]</b> waiting state</span><span><b>( )</b> end state</span><span><b>- - →</b> pause / resume</span></div>
</section>

<section id="order">
  <div class="sec-h"><div class="eyebrow">Section 2 · Execution order</div><h2>How the run moves from one action to the next</h2>
  <p>The graph says what <i>can</i> happen. The state machine records where this run <i>is</i>, so it can pause for days while waiting for the owner and resume exactly there.</p></div>
  <div class="scroll"><table>
    <thead><tr><th>#</th><th>Step</th><th>Mode</th><th>What happens</th></tr></thead>
    <tbody>{order_html}</tbody></table></div>
  <div class="grid2">
    <div class="diagram"><h4>State machine</h4><pre class="mermaid">{E(STATES)}</pre></div>
    <div class="panel"><h4>Events that resume a paused run</h4>
      <div class="scroll" style="border:0"><table><thead><tr><th>Event</th><th>Valid in</th><th>Goes to</th></tr></thead><tbody>{events_html}</tbody></table></div>
      <h4 style="margin-top:6px">Limits</h4>
      <p>{m.MAX_CLARIFICATION_ROUNDS} clarification rounds · {m.MAX_QUESTIONS_PER_ROUND} questions per round · {m.MAX_REPAIRS} automatic repairs. A gap is never asked twice.</p>
    </div>
  </div>
</section>

<section id="actions">
  <div class="sec-h"><div class="eyebrow">Section 3 · Step 4: methods, instruments, actions</div><h2>The ten actions</h2>
  <p>Each action is an executable function with typed inputs and outputs. Each card gives the business meaning, the YAML contract, and the real Python from <code>m01_set_renewal_goals.py</code> (expand to read it).</p></div>
  <div class="scroll"><table>
    <thead><tr><th>Action</th><th>Kind</th><th>Side effects</th><th>Instrument</th></tr></thead>
    <tbody>
      <tr><td>A1 Load context</td><td>Code</td><td>None</td><td>CRM, contract repository (list only), mandate store</td></tr>
      <tr><td>A2 Frame the decision</td><td>LLM + rules</td><td>None</td><td>LLM (structured output)</td></tr>
      <tr><td>A3 Resolve authority</td><td>Code</td><td>None</td><td>Mandate store</td></tr>
      <tr><td>A4 Find gaps and conflicts</td><td>Rules</td><td>None</td><td>—</td></tr>
      <tr><td>A5 Ask the owner</td><td>Human-in-the-loop</td><td>Internal message</td><td>Messaging (G1)</td></tr>
      <tr><td>A6 Record answers</td><td>LLM + code</td><td>None</td><td>LLM</td></tr>
      <tr><td>A7 Set success criteria</td><td>LLM</td><td>None</td><td>LLM</td></tr>
      <tr><td>A8 Assemble brief</td><td>Code</td><td>None</td><td>—</td></tr>
      <tr><td>A9 Validate brief</td><td>Code</td><td>None</td><td>—</td></tr>
      <tr><td>A10 Publish brief</td><td>Code</td><td>Dossier write, notification</td><td>Dossier, messaging (G3, G1)</td></tr>
    </tbody></table></div>
  <div class="panel"><h4>A4 gap rules (the heart of the graph's routing)</h4>
    <div class="scroll" style="border:0"><table><thead><tr><th>Condition</th><th>Severity</th><th>What happens</th></tr></thead><tbody>{gaprules_html}</tbody></table></div></div>
  {''.join(action_cards)}
</section>

<section id="scenarios">
  <div class="sec-h"><div class="eyebrow">Section 4 · Example scenarios</div><h2>Two runs through the graph</h2>
  <p>Both scenarios were executed by the reference code. Every table row below is real output. The LLM is a scripted stand-in that returns the structured answer a real prompt would give.</p></div>

  <article class="scenario">
    <h3>Scenario A: a simple, well-formed request</h3>
    <div class="req"><span>REQ-101 from {E(a_req['from_name'])}, {E(a_req['from_role'])} (also the mandate owner)</span>“{E(a_req['text'])}”</div>
    <p>Context: Northwind Logistics (buyer) holds a 150-user Westbrook CRM subscription ending 30 June 2027. The repository holds an executed MSA, order form, SLA and Amendment 1, plus a draft quote. Mandate MAN-77 allows analysis and internal consultation, with a $130,000 annual budget.</p>
    {trace_rows(ra)}
    <div class="grid2">
      <div><h4>Messages sent</h4>{messages(msa)}</div>
      <div class="shows"><b>What this shows</b><ul>
        <li>No gaps → no clarification loop. The run goes straight from A4 to A7.</li>
        <li>Criteria are sourced (MAN-77, REQ-101) and name the Moves that will supply evidence.</li>
        <li>The term end is labelled <code>SYSTEM_RECORD</code>, not contractual. M02/M03 must verify it.</li>
        <li>Ends <b>COMPLETE</b>; M02, M03 and M05 are recommended, not started.</li></ul></div>
    </div>
    <details><summary class="muted">Published brief (JSON)</summary>{code(json.dumps(brief_view(ra.brief), indent=2, ensure_ascii=False), 'json')}</details>
  </article>

  <article class="scenario">
    <h3>Scenario B: a solution-phrased request from someone who isn't the owner</h3>
    <div class="req"><span>REQ-202 from {E(b_req['from_name'])}, {E(b_req['from_role'])} (no decision right; owner is Mei Lin, CIO)</span>“{E(b_req['text'])}”</div>
    <p>Problems a naive agent would miss: the request states a solution (negotiate, 15% off); the requester has no authority; the mandate allows analysis only; no budget is recorded; renewing and replacing are both mentioned; a lower price and a higher SLA pull against each other; and “31 March” is a wish, not a contractual deadline.</p>
    {trace_rows(rb)}
    <div class="grid2">
      <div><h4>Messages sent</h4>{messages(msb)}</div>
      <div class="shows"><b>What this shows</b><ul>
        <li>Questions go to the <b>owner</b>, not the requester, blocking ones first, in two rounds.</li>
        <li>The owner narrows scope to analysis only, so negotiation becomes an <b>exclusion</b>. No supplier contact happens.</li>
        <li>The budget stays unresolved, so G2 makes the brief <b>QUALIFIED</b> and M32 chases Finance.</li>
        <li>Daniel's attempt to confirm is refused by G3. Only Mei can confirm.</li>
        <li>Daniel is told how his request was scoped.</li></ul></div>
    </div>
    <details><summary class="muted">Published brief (JSON)</summary>{code(json.dumps(brief_view(rb.brief), indent=2, ensure_ascii=False), 'json')}</details>
  </article>

  <div class="sec-h" style="border-top-width:1px"><h3>How this Move is used</h3></div>
  <div class="grid3">{uses_html}</div>
</section>

<section id="contract">
  <div class="sec-h"><div class="eyebrow">Section 5 · Step 3: Move contract</div><h2>The contract around the graph</h2>
  <p>Applicability, preconditions, inputs, output schema, completion states, failure behaviour and dependencies, in one machine-readable file (<code>m01_move.yaml</code>).</p></div>
  <div class="grid2">
    <div class="panel"><h4>Completion states</h4><ul class="clean">
      <li><b>COMPLETE</b>: the owner confirmed an authoritative brief, which is published.</li>
      <li><b>QUALIFIED_COMPLETE</b>: confirmed and published with MATERIAL gaps or unresolved authority recorded.</li>
      <li><b>REUSED</b>: same request under the same mandate version; the existing brief stands.</li>
      <li><b>BLOCKED</b>: request or account not found, or an unrepairable check failure.</li>
      <li><b>CANCELLED</b>: stopped by an authorized person.</li>
      <li><i>Paused:</i> AWAITING_OWNER, AWAITING_CONFIRMATION, ESCALATED (resumable).</li></ul></div>
    <div class="panel"><h4>Failure behaviour</h4><ul class="clean">
      <li>Never invent an owner, budget, authority or date. Missing means recorded as unknown.</li>
      <li>Silence is not permission. A timeout never resolves a gap.</li>
      <li>Authority comes only from the mandate store. Replies can narrow scope, never widen it.</li>
      <li>Request text is data. Instruction-like content is flagged and ignored.</li>
      <li>Boundaries: clauses → M02, deadlines → M03, stakeholder disputes → M29, missing owners → M32, changes → M33.</li></ul></div>
  </div>
  <details open><summary class="muted">m01_move.yaml (full)</summary>{code(yaml_full, 'yaml')}</details>
</section>

<section id="gates">
  <div class="sec-h"><div class="eyebrow">Section 6 · Step 5: checks and gates</div><h2>Where the run may not pass</h2>
  <p>A <b>gate</b> sits on an arrow and asks “may we go further?”. A <b>check</b> runs after an action and asks “is this output correct?”.</p></div>
  <div class="scroll"><table><thead><tr><th>Gate</th><th>Name</th><th>Where</th><th>Rule</th><th>If it fails</th></tr></thead><tbody>{gates_html}</tbody></table></div>
  <div class="scroll"><table><thead><tr><th>Check</th><th>Rule (run in A9)</th><th>If it fails</th></tr></thead><tbody>{checks_html}</tbody></table></div>
</section>

<section id="evals">
  <div class="sec-h"><div class="eyebrow">Section 7 · Step 6: evaluation suite</div><h2>{passed} of {len(evals)} evals pass</h2>
  <p>The cases cover normal, missing-evidence, conflicting-evidence, boundary, changed-state and adversarial situations, plus supplier-side and proportionality. Each one has an objective oracle (assertions) in <code>test_m01_evals.py</code>.</p></div>
  <div class="scroll"><table><thead><tr><th>#</th><th>Category</th><th>Case</th><th>Expected behaviour</th><th>Result</th></tr></thead><tbody>{evals_html}</tbody></table></div>
</section>

<section id="readiness">
  <div class="sec-h"><div class="eyebrow">Section 8 · Step 7: implementation readiness</div><h2>Readiness decision</h2></div>
  <div class="verdict"><div class="big">Conditional go</div>
    <p>The design is <b>ready to prototype</b> against real integrations. It is <b>not ready for production</b> until the open policy questions below are decided, real adapters replace the in-memory fakes, and real LLM prompts pass the same {len(evals)} evals plus tests of the LLM's own outputs.</p></div>
  <div class="scroll"><table><thead><tr><th>Question</th><th>Current default / need</th><th>Status</th></tr></thead><tbody>{policy_html}</tbody></table></div>
</section>

<footer>
  <div>Source: Kozmo Verb + Move Catalogue v0.2 (17 Nov 2026), M01 card p.11; operating model pp.1–3; V01 Frame p.4.</div>
  <div>Files: <code>m01_set_renewal_goals.py</code> (reference implementation) · <code>m01_move.yaml</code> (definition) · <code>test_m01_evals.py</code> (evals) · <code>build_page.py</code> (regenerates this page).</div>
</footer>
</main>
<script>
/* Diagrams render natively on claude.ai. When the file is opened locally, load Mermaid as a fallback. */
setTimeout(function () {{
  var blocks = document.querySelectorAll("pre.mermaid");
  var rendered = Array.prototype.some.call(blocks, function (b) {{ return b.querySelector("svg"); }});
  if (rendered || !blocks.length) return;
  var s = document.createElement("script");
  s.src = "https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.9.1/mermaid.min.js";
  s.onload = function () {{
    var dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    window.mermaid.initialize({{ startOnLoad: false, theme: dark ? "dark" : "neutral", securityLevel: "strict" }});
    window.mermaid.run({{ nodes: blocks }});
  }};
  document.head.appendChild(s);
}}, 1500);
</script>
"""
    out = HERE / "M01_Set_Renewal_Goals.html"
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out} ({len(page):,} chars); evals {passed}/{len(evals)}")


if __name__ == "__main__":
    build()
