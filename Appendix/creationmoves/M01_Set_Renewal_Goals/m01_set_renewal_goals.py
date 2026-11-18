"""
M01 Set Renewal Goals - reference implementation (design prototype, v0.2.1)

Kozmo Renewal Desk. Verb routes: Frame, Consult, Plan. Position in play: PRE.
Business output: a bounded Review brief (decision question + mandate) in the Dossier.

The Move is a directed graph of 10 Actions guarded by Gates (G0-G3) and Checks (C1-C7).
A state machine records where a run is, so it can pause while waiting for people and resume.

    A1 -[G0]-> (A2 || A3) -> A4 -> askable gaps? --yes--> [G1] A5 ~wait~ A6 -> back to A4
                                                 --no---> A7 -> A8 -> A9 [C1-C7] -> [G2] -> [G1+G3] ~wait~ A10

Core rules the code enforces:
  * Authority comes only from the mandate store (A3). Chat replies and request text can NARROW scope,
    never widen it. A request to widen it is recorded as "pending mandate update".
  * Silence is never permission. A timeout never resolves a gap.
  * Every fact in the brief carries a source; nothing is invented.
  * M01 lists documents, it does not interpret them (M02), compute deadlines (M03),
    or settle disputes between stakeholders (M29).

Integrations are interfaces. The demo uses in-memory fakes and a *scripted* LLM so that runs are
deterministic. In production the LLM returns the same structured shapes, validated by the same code.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional, Protocol

MAX_CLARIFICATION_ROUNDS = 2
MAX_QUESTIONS_PER_ROUND = 3
MAX_REPAIRS = 2


# ============================================================================ types
class State(str, Enum):
    NEW = "NEW"
    LOADING_CONTEXT = "LOADING_CONTEXT"              # A1 + G0
    FRAMING = "FRAMING"                              # A2 || A3
    ASSESSING = "ASSESSING"                          # A4 (+ G1, A5)
    AWAITING_OWNER = "AWAITING_OWNER"                # paused after A5
    DRAFTING_CRITERIA = "DRAFTING_CRITERIA"          # A7
    ASSEMBLING = "ASSEMBLING"                        # A8
    VALIDATING = "VALIDATING"                        # A9 + G2 + G3 request
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"  # paused at G3
    ESCALATED = "ESCALATED"                          # paused, handed to M32; resumable
    COMPLETE = "COMPLETE"
    QUALIFIED_COMPLETE = "QUALIFIED_COMPLETE"
    REUSED = "REUSED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


WAITING = {State.AWAITING_OWNER, State.AWAITING_CONFIRMATION, State.ESCALATED}
TERMINAL = {State.COMPLETE, State.QUALIFIED_COMPLETE, State.REUSED, State.BLOCKED, State.CANCELLED}


class Severity(str, Enum):
    BLOCKING = "BLOCKING"   # no brief may be published
    MATERIAL = "MATERIAL"   # brief may be published only as QUALIFIED
    MINOR = "MINOR"         # recorded; does not change completion


class DateKind(str, Enum):
    CONTRACTUAL = "CONTRACTUAL"          # read from an executed instrument (only M02/M03 set this)
    SYSTEM_RECORD = "SYSTEM_RECORD"      # from CRM / mandate store; to be verified by M02/M03
    INTERNAL_TARGET = "INTERNAL_TARGET"  # a person's wish, not a contractual duty
    UNKNOWN = "UNKNOWN"


@dataclass
class SourceRef:
    system: str   # request | crm | contract_repo | mandate_store | answer
    ref: str


@dataclass
class DocRef:
    doc_id: str
    doc_type: str          # MSA | ORDER_FORM | SLA | AMENDMENT | QUOTE | NOTE ...
    version: str
    status: str            # EXECUTED | DRAFT
    effective_date: str
    visibility: str        # SHARED | BUYER_PRIVATE | SUPPLIER_PRIVATE
    source: SourceRef


@dataclass
class ContextBundle:                       # A1 output
    request: dict
    account: dict
    subscription: Optional[dict]
    other_subscriptions: list[dict]
    documents: list[DocRef]
    withheld_documents: int                # filtered by information barrier
    headline_facts: dict                   # name -> {"value", "kind", "source"}
    mandate: Optional[dict]
    existing_brief: Optional[dict]
    missing: list[str] = field(default_factory=list)


@dataclass
class Framing:                             # A2 output
    desired_outcome: str
    decision_question: str
    perspective: str                       # BUYER | SUPPLIER | UNKNOWN
    requested_actions: list[str]           # ANALYZE | CONSULT_INTERNAL | NEGOTIATE | CONTACT_COUNTERPARTY ...
    candidate_goals: list[dict]
    stated_dates: list[dict]               # {"label", "date", "kind", "source"}
    decision_paths: list[str]              # RENEW | RENEW_CHANGED | REPLACE | EXIT
    solution_signals: list[str]
    injection_signals: list[str]
    priority_conflicts: list[dict]         # {"text", "between_stakeholders": bool}
    request_kind: str                      # FULL_REVIEW | QUICK_COMPARISON


@dataclass
class Authority:                           # A3 output - the ONLY source of authority
    owner: Optional[dict]
    delegates: list[dict]
    requester: dict
    requester_has_rights: bool
    decision_rights: list[str]
    allowed_actions: list[str]
    budget: Optional[dict]
    deadline: Optional[dict]
    allowed_contact: list[str]             # INTERNAL | COUNTERPARTY
    approvers: list[dict]
    mandate_id: Optional[str]
    mandate_version: Optional[int]
    mandate_valid_until: Optional[str]


@dataclass
class Gap:                                 # A4 output
    gap_id: str
    kind: str                              # OWNER | AUTHORITY | PERSPECTIVE | SCOPE | BUDGET | PRIORITY | DATE | EVIDENCE | SAFETY
    severity: Severity
    description: str
    question: Optional[str] = None
    ask_to: Optional[str] = None
    suggest_move: Optional[str] = None
    answerable: bool = True                # False = a chat answer cannot resolve it (needs mandate update)


@dataclass
class Answer:                              # A6 output
    gap_id: str
    text: str
    answered_by: str
    message_ref: str
    resolves: bool


@dataclass
class Criterion:                           # A7 output
    criterion_id: str
    statement: str
    priority: str                          # MUST | SHOULD
    measure: str
    target: str
    source: SourceRef
    depends_on: list[str] = field(default_factory=list)   # Moves whose output the target needs


@dataclass
class ReviewBrief:                         # A8 output, published by A10
    brief_id: str
    version: int
    request_id: str
    mandate_id: Optional[str]
    mandate_version: Optional[int]
    account_id: str
    subscription_id: Optional[str]
    perspective: str
    decision_question: str
    desired_outcome: str
    decision_paths: list[str]
    mode: str                              # FULL | LIGHT
    responsibility: dict
    authorized_actions: list[str]
    scope_in: list[str]
    exclusions: list[str]
    budget: Optional[dict]
    dates: list[dict]
    allowed_contact: list[str]
    success_criteria: list[Criterion]
    evidence_inventory: list[DocRef]
    open_questions: list[dict]
    unresolved_authority: list[str]
    recommended_next_moves: list[dict]     # advisory; the Manager decides what to commission
    status: str = "DRAFT"                  # DRAFT | CONFIRMED | QUALIFIED
    confirmed_by: Optional[str] = None


# ============================================================================ ports
class Sources(Protocol):
    def get_request(self, request_id: str) -> Optional[dict]: ...
    def get_account(self, account_id: str) -> Optional[dict]: ...
    def list_subscriptions(self, account_id: str) -> list[dict]: ...
    def list_documents(self, account_id: str, subscription_id: Optional[str]) -> list[DocRef]: ...
    def get_mandate(self, account_id: str, subscription_id: Optional[str]) -> Optional[dict]: ...
    def get_current_brief(self, account_id: str, subscription_id: Optional[str]) -> Optional[dict]: ...


class LLM(Protocol):
    def frame_request(self, request_text: str, context: dict) -> dict: ...
    def parse_answers(self, questions: list[dict], reply_text: str) -> dict: ...
    def draft_criteria(self, framing: dict, answers: list[dict], authority: dict) -> dict: ...


class Messenger(Protocol):
    def send(self, to_person_id: str, channel: str, subject: str, body: str) -> str: ...


class Dossier(Protocol):
    def publish(self, section: str, payload: dict) -> str: ...


# ============================================================================ helpers
def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def _norm_measure(m: str) -> str:
    return re.sub(r"\s*\(.*?\)", "", m).strip().lower()


def _stem(action: str) -> str:
    return action.split("_")[0].lower()[:6]


SOLUTION_PATTERNS = [r"\bnegotiate\b", r"\bget \d+\s?% off\b", r"\b\d+\s?% (?:discount|off)\b",
                     r"\bpush the sla\b", r"\bcancel\b", r"\bswitch to\b", r"\bsign\b"]
# C1 only rejects *committed* solutions. "Should we renew or cancel?" is a valid question.
COMMITTED_SOLUTION_PATTERNS = SOLUTION_PATTERNS[:4]
INJECTION_PATTERNS = [r"\bsystem\s*:", r"ignore (?:all|previous|the) (?:rules|instructions|policy)",
                      r"you are (?:now )?authori[sz]ed", r"\bapproved by (?:the )?system\b"]


def _find(patterns: list[str], text: str) -> list[str]:
    out = []
    for p in patterns:
        m = re.search(p, text, flags=re.IGNORECASE)
        if m:
            out.append(m.group(0).lower())
    return out


# ============================================================================ actions
def a1_load_context(src: Sources, account_id: str, subscription_id: Optional[str],
                    request_id: str) -> ContextBundle:
    """A1 Load context. Code, read-only. Lists documents and headline facts; interprets nothing (M02)."""
    request, account = src.get_request(request_id), src.get_account(account_id)
    if request is None:
        raise LookupError("REQUEST_NOT_FOUND")
    if account is None:
        raise LookupError("ACCOUNT_NOT_FOUND")
    subs = [s for s in src.list_subscriptions(account_id) if s.get("status", "ACTIVE") == "ACTIVE"]
    if subscription_id is None and len(subs) == 1:
        subscription_id = subs[0]["id"]                       # unambiguous: only one active subscription
    subscription = next((s for s in subs if s["id"] == subscription_id), None)
    missing: list[str] = []
    if subscription_id and subscription is None:
        missing.append("subscription record")
    # Information barrier: never load the other side's private documents.
    our_side = account.get("our_side", "BUYER")
    barred = "SUPPLIER_PRIVATE" if our_side == "BUYER" else "BUYER_PRIVATE"
    all_docs = src.list_documents(account_id, subscription_id)
    docs = [d for d in all_docs if d.visibility != barred]
    if not any(d.status == "EXECUTED" for d in docs):
        missing.append("any executed agreement")              # completeness is judged by M02
    mandate = src.get_mandate(account_id, subscription_id)
    if mandate is None:
        missing.append("mandate record")
    headline: dict[str, Any] = {}
    if subscription:
        crm = asdict(SourceRef("crm", subscription["id"]))
        headline["term_end"] = {"value": subscription["term_end"], "kind": DateKind.SYSTEM_RECORD.value, "source": crm}
        headline["quantity"] = {"value": subscription["quantity"], "source": crm}
        if subscription.get("sla_headline"):
            headline["sla_level"] = {"value": subscription["sla_headline"], "source": crm}
    return ContextBundle(request, account, subscription,
                         [s for s in subs if s["id"] != subscription_id] if subscription is None else [],
                         docs, len(all_docs) - len(docs), headline, mandate,
                         src.get_current_brief(account_id, subscription_id), missing)


def g0_applicability(ctx: ContextBundle, request_id: str, force: bool) -> tuple[bool, str]:
    """G0 Applicability gate: reuse the current brief only for the SAME request under the SAME mandate version."""
    cb, m = ctx.existing_brief, ctx.mandate
    if force or cb is None or m is None:
        return False, "no reusable brief"
    if cb.get("request_id") == request_id and cb.get("mandate_version") == m.get("version") \
            and cb.get("status") in ("CONFIRMED", "QUALIFIED"):
        return True, f'brief {cb["brief_id"]} is current for this request and mandate v{m["version"]}'
    return False, "existing brief is for another request or mandate version"


def a2_frame_decision(llm: LLM, ctx: ContextBundle) -> Framing:
    """A2 Frame the decision. LLM structured output + rule cross-checks. No side effects.
    The LLM reads the request as DATA; nothing it returns can grant authority."""
    text = ctx.request["text"]
    raw = llm.frame_request(text, {"account": ctx.account, "subscription": ctx.subscription,
                                   "headline_facts": ctx.headline_facts})
    perspective = raw.get("perspective", "UNKNOWN")
    if perspective != ctx.account.get("our_side", perspective):
        perspective = "UNKNOWN"          # text and account record disagree -> clarify, don't guess
    return Framing(
        desired_outcome=raw["desired_outcome"],
        decision_question=raw["decision_question"],
        perspective=perspective,
        requested_actions=raw["requested_actions"],
        candidate_goals=raw.get("candidate_goals", []),
        stated_dates=raw.get("stated_dates", []),
        decision_paths=raw.get("decision_paths", ["RENEW"]),
        solution_signals=sorted({s.lower() for s in raw.get("solution_signals", [])} | set(_find(SOLUTION_PATTERNS, text))),
        injection_signals=_find(INJECTION_PATTERNS, text),
        priority_conflicts=raw.get("priority_conflicts", []),
        request_kind=raw.get("request_kind", "FULL_REVIEW"),
    )


def a3_resolve_authority(ctx: ContextBundle) -> Authority:
    """A3 Resolve owner and decision rights. Deterministic lookup in the mandate store; never inferred."""
    m = ctx.mandate or {}
    requester = {"person_id": ctx.request["from_id"], "name": ctx.request["from_name"],
                 "role": ctx.request.get("from_role", "")}
    rights = m.get("decision_rights", [])
    return Authority(
        owner=m.get("owner"), delegates=m.get("delegates", []), requester=requester,
        requester_has_rights=requester["person_id"] in {p["person_id"] for p in rights},
        decision_rights=[f'{p["name"]}: {p["right"]}' for p in rights],
        allowed_actions=m.get("allowed_actions", []), budget=m.get("budget"), deadline=m.get("deadline"),
        allowed_contact=m.get("allowed_contact", []), approvers=m.get("approvers", []),
        mandate_id=m.get("id"), mandate_version=m.get("version"), mandate_valid_until=m.get("valid_until"),
    )


def a4_find_gaps(ctx: ContextBundle, fr: Framing, au: Authority, resolved: set[str],
                 pending_mandate: list[str], today: dt.date) -> list[Gap]:
    """A4 Find gaps and conflicts. Deterministic rules over A1-A3 outputs."""
    gaps: list[Gap] = []
    owner_id = au.owner["person_id"] if au.owner else None
    if ctx.mandate is None:
        gaps.append(Gap("G-MANDATE", "OWNER", Severity.BLOCKING, "No mandate record exists for this account.",
                        suggest_move="M32", answerable=False))
    elif au.owner is None or not au.owner.get("active", True):
        gaps.append(Gap("G-OWNER", "OWNER", Severity.BLOCKING,
                        "No active accountable renewal owner is recorded.", suggest_move="M32", answerable=False))
    if au.mandate_valid_until and _date(au.mandate_valid_until) < today:
        gaps.append(Gap("G-MANDATE-EXPIRED", "AUTHORITY", Severity.BLOCKING,
                        f"The mandate expired on {au.mandate_valid_until}.",
                        f"The mandate for this renewal expired on {au.mandate_valid_until}. "
                        "Please renew it in the mandate store so the Review can continue.",
                        owner_id, answerable=False))
    if ctx.subscription is None and ctx.other_subscriptions:
        names = ", ".join(f'{s["id"]} ({s["product"]})' for s in ctx.other_subscriptions)
        gaps.append(Gap("G-SUBSCRIPTION", "SCOPE", Severity.BLOCKING,
                        "Several active subscriptions and the request does not say which one is in scope.",
                        f"Which subscription(s) should this Review cover: {names}? Should any be co-termed?",
                        owner_id))
    if fr.perspective == "UNKNOWN":
        gaps.append(Gap("G-PERSPECTIVE", "PERSPECTIVE", Severity.BLOCKING,
                        "Buyer or supplier perspective is unclear (request and account record disagree).",
                        "Are we preparing this Review for our side as the buyer or as the supplier?", owner_id))
    beyond = [a for a in fr.requested_actions if a not in au.allowed_actions]
    if beyond and au.owner:
        allowed_txt = ", ".join(a.lower().replace("_", " ") for a in au.allowed_actions) or "nothing"
        gaps.append(Gap("G-AUTH-ACTIONS", "AUTHORITY", Severity.BLOCKING,
                        f"Requested actions {beyond} are outside the mandate (allowed: {au.allowed_actions}).",
                        f"The request asks for {', '.join(a.lower().replace('_', ' ') for a in beyond)}. "
                        f"The current mandate allows: {allowed_txt}. Should this Review stay within that? "
                        "If more is needed, the mandate itself must be updated.", owner_id))
    for a in pending_mandate:
        gaps.append(Gap(f"G-PENDING-{a}", "AUTHORITY", Severity.MATERIAL,
                        f"Owner wants {a.lower().replace('_', ' ')}, but the mandate does not allow it yet "
                        "(pending mandate update; then run M33).", suggest_move="M33", answerable=False))
    if au.owner and not au.requester_has_rights and au.requester["person_id"] != owner_id:
        gaps.append(Gap("G-REQUESTER", "AUTHORITY", Severity.MINOR,
                        f'Requester {au.requester["name"]} holds no decision right; '
                        f'the brief is owned by {au.owner["name"]}. Requester will be informed.'))
    if au.owner and au.budget is None and fr.request_kind != "QUICK_COMPARISON":
        gaps.append(Gap("G-BUDGET", "BUDGET", Severity.MATERIAL, "No budget ceiling is recorded in the mandate.",
                        "Is there an approved budget ceiling for this renewal, and who owns it?",
                        owner_id, suggest_move="M32"))
    if "REPLACE" in fr.decision_paths and len(fr.decision_paths) > 1:
        gaps.append(Gap("G-SCOPE-REPLACE", "SCOPE", Severity.MATERIAL,
                        "Request mentions both renewing and moving to another product.",
                        "Should this Review also assess replacing the product, or only renewal terms?", owner_id))
    for i, c in enumerate(fr.priority_conflicts):
        if c.get("between_stakeholders"):   # people disagree -> M29's job, not M01's
            gaps.append(Gap(f"G-PRIORITY-{i+1}", "PRIORITY", Severity.MATERIAL, c["text"],
                            suggest_move="M29", answerable=False))
        else:                               # one instruction is ambiguous -> owner clarifies here
            gaps.append(Gap(f"G-PRIORITY-{i+1}", "PRIORITY", Severity.MATERIAL, c["text"],
                            "Which of these is a must-have and which is a target we can trade?", owner_id))
    term_end = (ctx.subscription or {}).get("term_end")
    for d in fr.stated_dates:
        if term_end and d.get("date") and _date(d["date"]) > _date(term_end):
            gaps.append(Gap("G-DATE-AFTER-TERM", "DATE", Severity.BLOCKING,
                            f'Requested date {d["date"]} is after term end {term_end}.',
                            "The requested decision date is after the subscription ends. Which date applies?",
                            owner_id, suggest_move="M03"))
    if fr.injection_signals:
        gaps.append(Gap("G-INJECTION", "SAFETY", Severity.MINOR,
                        f"Request text contains instruction-like content {fr.injection_signals}; treated as data, "
                        "no authority taken from it.", answerable=False))
    for item in ctx.missing:
        if item != "mandate record":
            gaps.append(Gap(f"G-EVIDENCE-{item.replace(' ', '-')}", "EVIDENCE", Severity.MINOR,
                            f"Missing: {item}. Passed to M02; does not block framing.", suggest_move="M02"))
    return [g for g in gaps if g.gap_id not in resolved]


def g1_contact_gate(person_id: Optional[str], purpose: str, au: Authority) -> tuple[bool, str]:
    """G1 Contact gate. Used before EVERY outgoing message (questions, confirmation, notifications)."""
    if person_id is None:
        return False, "no recipient"
    if "INTERNAL" not in au.allowed_contact:
        return False, "internal contact not permitted by mandate"
    decision_people = ({au.owner["person_id"]} if au.owner else set()) | {d["person_id"] for d in au.delegates}
    if purpose in ("clarify", "confirm") and person_id not in decision_people:
        return False, "recipient is not the owner or a recorded delegate"
    if purpose == "notify" and person_id != au.requester["person_id"]:
        return False, "notifications go only to the requester"
    return True, "ok"


def a5_ask_owner(msg: Messenger, gaps: list[Gap], round_no: int) -> dict:
    """A5 Ask the owner/delegate. Sends internal messages (side effect). Runs only for gaps that passed G1."""
    by_person: dict[str, list[Gap]] = {}
    for g in gaps[:MAX_QUESTIONS_PER_ROUND]:
        by_person.setdefault(g.ask_to, []).append(g)
    sent = []
    for person, gs in by_person.items():
        body = "\n".join(f"{i+1}. {g.question}" for i, g in enumerate(gs))
        ref = msg.send(person, "internal", f"Renewal Review brief - clarification round {round_no}", body)
        sent.append({"to": person, "message_ref": ref})
    return {"round": round_no, "sent": sent, "recipients": set(by_person),
            "questions": [{"gap_id": g.gap_id, "question": g.question, "answerable": g.answerable}
                          for g in gaps[:MAX_QUESTIONS_PER_ROUND]]}


SAFE_UPDATE_FIELDS = {"requested_actions", "decision_paths", "priority_conflicts", "perspective"}


def a6_record_answers(llm: LLM, outstanding: dict, reply_text: str, replied_by: str, reply_ref: str,
                      fr: Framing, au: Authority) -> tuple[list[Answer], dict, list[str], list[str]]:
    """A6 Record answers. LLM parses the reply; CODE decides what may change.
    Returns (answers, applied_updates, pending_mandate_actions, rejected_updates)."""
    parsed = llm.parse_answers(outstanding["questions"], reply_text)
    answerable = {q["gap_id"]: q["answerable"] for q in outstanding["questions"]}
    answers = [Answer(a["gap_id"], a["text"], replied_by, reply_ref,
                      a["resolves"] and answerable.get(a["gap_id"], False)) for a in parsed["answers"]]
    applied, pending, rejected = {}, [], []
    for k, v in parsed.get("updates", {}).items():
        if k not in SAFE_UPDATE_FIELDS:
            rejected.append(f"{k}: not changeable by a reply")
        elif k == "requested_actions":
            widened = [a for a in v if a not in au.allowed_actions]
            pending += widened                           # owner wants more than the mandate allows
            applied[k] = [a for a in v if a in au.allowed_actions] or ["ANALYZE"]
        elif k == "perspective" and fr.perspective != "UNKNOWN":
            rejected.append("perspective: already established")
        else:
            applied[k] = v
    return answers, applied, pending, rejected


def a7_set_success_criteria(llm: LLM, fr: Framing, answers: list[Answer], au: Authority,
                            pending: list[str]) -> tuple[list[Criterion], list[str]]:
    """A7 Set success criteria and exclusions. LLM drafts from goals + answers; code adds mandatory exclusions."""
    raw = llm.draft_criteria(asdict(fr), [asdict(a) for a in answers], asdict(au))
    crits = [Criterion(c["id"], c["statement"], c["priority"], c["measure"], c["target"],
                       SourceRef(**c["source"]), c.get("depends_on", [])) for c in raw["criteria"]]
    exclusions = list(raw.get("exclusions", []))
    for a in sorted(set(fr.requested_actions + pending) - set(au.allowed_actions)):
        if not any(_stem(a) in e.lower() for e in exclusions):
            note = "pending mandate update" if a in pending else "not authorized by the mandate"
            exclusions.append(f"{a.replace('_', ' ').title()}: {note}.")
    return crits, exclusions


def recommend_next_moves(ctx: ContextBundle, fr: Framing, crits: list[Criterion], gaps: list[Gap],
                         mode: str) -> list[dict]:
    """Advisory rule table. The Manager decides what to commission; M01 starts nothing."""
    nxt = []
    if ctx.documents:
        nxt.append({"move": "M02", "why": "Build the cited agreement baseline from the listed documents."})
    if mode == "FULL":
        nxt.append({"move": "M03", "why": "Verify term end and notice rules; produce the deadline register."})
    text = " ".join(_norm_measure(c.measure) for c in crits)
    if any(k in text for k in ("cost", "licence", "license", "users", "spend")):
        nxt.append({"move": "M05", "why": "Cost or quantity goals need observed usage."})
    if any(k in text for k in ("sla", "uptime", "support level")):
        nxt.append({"move": "M04", "why": "Service-level goals need the supplier's delivery history."})
    if "REPLACE" in fr.decision_paths:
        nxt.append({"move": "M13", "why": "Replacement is in scope; define what a replacement must do."})
    for g in gaps:
        if g.suggest_move in ("M29", "M32", "M33") and g.severity != Severity.MINOR:
            nxt.append({"move": g.suggest_move, "why": g.description})
    return nxt


def a8_assemble_brief(ctx: ContextBundle, fr: Framing, au: Authority, crits: list[Criterion],
                      exclusions: list[str], gaps: list[Gap], version: int) -> ReviewBrief:
    """A8 Assemble brief. Code only: copies sourced values into the schema; creates no new facts."""
    unresolved = [g.description for g in gaps if g.kind in ("AUTHORITY", "BUDGET", "OWNER")
                  and g.severity != Severity.MINOR]
    dates = list(fr.stated_dates)
    if "term_end" in ctx.headline_facts:
        h = ctx.headline_facts["term_end"]
        dates.append({"label": "Subscription term end (system record; M02/M03 verify)",
                      "date": h["value"], "kind": h["kind"], "source": h["source"]})
    if au.deadline:
        dates.append({"label": "Mandate deadline", "date": au.deadline["date"], "kind": DateKind.INTERNAL_TARGET.value,
                      "source": asdict(SourceRef("mandate_store", au.mandate_id or ""))})
    mode = "LIGHT" if fr.request_kind == "QUICK_COMPARISON" else "FULL"
    return ReviewBrief(
        brief_id=f'BRF-{ctx.account["id"]}-{ctx.request["id"]}', version=version, request_id=ctx.request["id"],
        mandate_id=au.mandate_id, mandate_version=au.mandate_version,
        account_id=ctx.account["id"], subscription_id=(ctx.subscription or {}).get("id"),
        perspective=fr.perspective, decision_question=fr.decision_question, desired_outcome=fr.desired_outcome,
        decision_paths=fr.decision_paths, mode=mode,
        responsibility={"accountable": au.owner, "prepared_by": "Kozmo Renewal Manager (agent)",
                        "approvers": au.approvers},
        authorized_actions=[a for a in fr.requested_actions if a in au.allowed_actions],
        scope_in=[f"Decision path: {p}" for p in fr.decision_paths],
        exclusions=exclusions, budget=au.budget, dates=dates, allowed_contact=au.allowed_contact,
        success_criteria=crits, evidence_inventory=ctx.documents,
        open_questions=[{"gap_id": g.gap_id, "severity": g.severity.value, "description": g.description,
                         "next": g.suggest_move} for g in gaps],
        unresolved_authority=unresolved,
        recommended_next_moves=recommend_next_moves(ctx, fr, crits, gaps, mode),
    )


def a9_validate_brief(b: ReviewBrief, au: Authority, fr: Framing, known_refs: set[str]) -> list[str]:
    """A9 Validate brief. Checks C1-C7. Returns failure codes; empty = pass."""
    f = []
    q = b.decision_question.strip()
    if not q.endswith("?") or _find(COMMITTED_SOLUTION_PATTERNS, q):
        f.append("C1 decision question states a solution or is not a question")
    acc = b.responsibility.get("accountable")
    if not acc or acc.get("name") == b.responsibility.get("prepared_by"):
        f.append("C2 accountable owner missing or confused with the preparer")
    for fld in ("decision_question", "perspective", "account_id", "request_id"):
        if not getattr(b, fld):
            f.append(f"C3 required field empty: {fld}")
    if b.mode == "FULL" and not any(c.priority == "MUST" for c in b.success_criteria):
        f.append("C4 no MUST criterion")
    if any(not c.measure or not c.target for c in b.success_criteria):
        f.append("C4 criterion not measurable")
    musts = [_norm_measure(c.measure) for c in b.success_criteria if c.priority == "MUST"]
    if len(musts) != len(set(musts)):
        f.append("C4 two MUST criteria target the same measure")
    if any(a not in au.allowed_actions for a in b.authorized_actions):
        f.append("C5 brief authorizes an action outside the mandate")
    for a in fr.requested_actions:
        if a not in au.allowed_actions and not any(_stem(a) in e.lower() for e in b.exclusions):
            f.append(f"C5 unauthorized request {a} not listed as exclusion")
    for d in b.dates:
        if d.get("kind") not in {k.value for k in DateKind} or not d.get("source"):
            f.append(f'C6 date "{d.get("label")}" lacks a kind or source')
        if d.get("kind") == DateKind.CONTRACTUAL.value and d["source"].get("system") != "contract_repo":
            f.append(f'C6 date "{d.get("label")}" labelled contractual without a contract source')
    for c in b.success_criteria:
        if c.source.ref not in known_refs:
            f.append(f"C7 criterion {c.criterion_id} cites unknown source {c.source.ref}")
    if b.budget is not None and b.budget.get("source", {}).get("system") != "mandate_store":
        f.append("C7 budget does not come from the mandate store")
    return f


def g2_authority_gate(b: ReviewBrief) -> str:
    """G2 Authority gate. BLOCKING never reaches here; MATERIAL or unresolved authority -> QUALIFIED."""
    if b.unresolved_authority or any(q["severity"] == "MATERIAL" for q in b.open_questions):
        return "QUALIFIED"
    return "AUTHORITATIVE"


def a10_publish(dossier: Dossier, b: ReviewBrief) -> str:
    """A10 Publish. Writes the confirmed version to the Dossier (only after G3)."""
    return dossier.publish("decision_question_and_mandate", json.loads(json.dumps(asdict(b), default=str)))


# ============================================================================ graph runner / state machine
class M01Run:
    """Executes the M01 graph. run() advances until a WAITING or TERMINAL state; resume(event) continues."""

    REPAIR_ROUTE = {"C1": "FRAMING", "C4": "DRAFTING_CRITERIA"}   # other check failures are code defects

    def __init__(self, inputs: dict, src: Sources, llm: LLM, msg: Messenger, dossier: Dossier,
                 today: dt.date = dt.date(2026, 11, 17)):
        self.inputs, self.src, self.llm, self.msg, self.dossier, self.today = inputs, src, llm, msg, dossier, today
        self.state = State.NEW
        self.trace: list[str] = []
        self.reason = ""
        self.answers: list[Answer] = []
        self._reset()

    def _reset(self) -> None:
        self.ctx: Optional[ContextBundle] = None
        self.framing: Optional[Framing] = None
        self.authority: Optional[Authority] = None
        self.gaps: list[Gap] = []
        self.resolved: set[str] = set()
        self.asked: set[str] = set()
        self.pending_mandate: list[str] = []
        self.rounds = self.repairs = 0
        self.outstanding: Optional[dict] = None
        self.criteria: list[Criterion] = []
        self.exclusions: list[str] = []
        self.brief: Optional[ReviewBrief] = None
        self.publication: Optional[str] = None

    def _go(self, new: State, note: str = "") -> None:
        self.trace.append(f"{self.state.value:>22} -> {new.value:<22} {note}")
        self.state = new

    def _note(self, text: str) -> None:
        self.trace.append(f"{'':>22}    {text}")

    def _send(self, person_id: str, purpose: str, subject: str, body: str) -> Optional[str]:
        ok, why = g1_contact_gate(person_id, purpose, self.authority)
        if not ok:
            self._note(f"G1 refused message to {person_id} ({purpose}): {why}")
            return None
        return self.msg.send(person_id, "internal", subject, body)

    def _known_refs(self) -> set[str]:
        refs = {self.ctx.request["id"]} | {d.doc_id for d in self.ctx.documents}
        refs |= {a.message_ref for a in self.answers}
        if self.authority.mandate_id:
            refs.add(self.authority.mandate_id)
        return refs

    def run(self) -> State:
        while self.state not in WAITING | TERMINAL:
            self._step()
        return self.state

    def _step(self) -> None:  # noqa: C901 - one branch per graph node, kept explicit on purpose
        s = self.state
        if s == State.NEW:
            self._go(State.LOADING_CONTEXT, "start")

        elif s == State.LOADING_CONTEXT:
            try:
                self.ctx = a1_load_context(self.src, self.inputs["account_id"], self.inputs.get("subscription_id"),
                                           self.inputs["request_id"])
            except LookupError as e:
                self.reason = str(e)
                self._go(State.BLOCKED, f"A1 failed: {e}")
                return
            reuse, why = g0_applicability(self.ctx, self.inputs["request_id"], self.inputs.get("force_reframe", False))
            if reuse:
                self.reason = why
                self._go(State.REUSED, f"G0: {why}")
                return
            self._go(State.FRAMING, f"A1 {len(self.ctx.documents)} docs listed, {self.ctx.withheld_documents} "
                                    f"withheld by barrier, missing={self.ctx.missing}; G0: {why}")

        elif s == State.FRAMING:
            with ThreadPoolExecutor(max_workers=2) as pool:            # A2 || A3, then join
                f2 = pool.submit(a2_frame_decision, self.llm, self.ctx)
                f3 = pool.submit(a3_resolve_authority, self.ctx)
                self.framing, self.authority = f2.result(), f3.result()
            self._go(State.ASSESSING, f"A2||A3 owner={self.authority.owner and self.authority.owner['name']}, "
                                      f"perspective={self.framing.perspective}, signals={self.framing.solution_signals}")

        elif s == State.ASSESSING:
            self.gaps = a4_find_gaps(self.ctx, self.framing, self.authority, self.resolved,
                                     self.pending_mandate, self.today)
            if any(g.kind == "OWNER" for g in self.gaps):
                self.reason = "no mandate or no active owner"
                self._go(State.ESCALATED, "A4: no accountable owner -> handed to M32; waiting for owner_assigned")
                return
            askable = sorted([g for g in self.gaps if g.question and g.severity != Severity.MINOR
                              and g.gap_id not in self.asked], key=lambda g: g.severity != Severity.BLOCKING)
            if askable and self.rounds < MAX_CLARIFICATION_ROUNDS:
                allowed = []
                for g in askable:
                    ok, why = g1_contact_gate(g.ask_to, "clarify", self.authority)
                    allowed.append(g) if ok else self._note(f"G1 refused {g.gap_id}: {why}")
                if allowed:
                    self.rounds += 1
                    self.outstanding = a5_ask_owner(self.msg, allowed, self.rounds)
                    self.asked |= {q["gap_id"] for q in self.outstanding["questions"]}
                    self._go(State.AWAITING_OWNER, f"A4 {len(self.gaps)} gaps -> G1 pass -> A5 asked "
                                                   f"{[q['gap_id'] for q in self.outstanding['questions']]}")
                    return
            blocking = [g.gap_id for g in self.gaps if g.severity == Severity.BLOCKING]
            if blocking:
                self.reason = f"blocking gaps unresolved: {blocking}"
                self._go(State.ESCALATED, f"A4: {blocking} unresolved -> M32; brief NOT published")
                return
            self._go(State.DRAFTING_CRITERIA, f"A4 nothing left to ask ({len(self.gaps)} gaps recorded)")

        elif s == State.DRAFTING_CRITERIA:
            self.criteria, self.exclusions = a7_set_success_criteria(self.llm, self.framing, self.answers,
                                                                     self.authority, self.pending_mandate)
            self._go(State.ASSEMBLING, f"A7 {len(self.criteria)} criteria, {len(self.exclusions)} exclusions")

        elif s == State.ASSEMBLING:
            version = (self.brief.version + 1) if self.brief else 1
            self.brief = a8_assemble_brief(self.ctx, self.framing, self.authority, self.criteria,
                                           self.exclusions, self.gaps, version)
            self._go(State.VALIDATING, f"A8 brief v{version} ({self.brief.mode})")

        elif s == State.VALIDATING:
            fails = a9_validate_brief(self.brief, self.authority, self.framing, self._known_refs())
            if fails:
                routes = {self.REPAIR_ROUTE.get(x[:2]) for x in fails}
                if None not in routes and self.repairs < MAX_REPAIRS:
                    self.repairs += 1
                    target = State.FRAMING if "FRAMING" in routes else State.DRAFTING_CRITERIA
                    self._go(target, f"A9 failed {fails} -> repair #{self.repairs}")
                    return
                self.reason = f"checks failing: {fails}"
                self._go(State.BLOCKED, "A9 failed and cannot be repaired automatically")
                return
            level = g2_authority_gate(self.brief)
            self.brief.status = "QUALIFIED" if level == "QUALIFIED" else "DRAFT"
            ref = self._send(self.authority.owner["person_id"], "confirm",
                             f"Please confirm Review brief v{self.brief.version}",
                             f"{self.brief.decision_question}\n(Will be published as: {level})")
            if ref is None:
                self.reason = "cannot reach owner for confirmation"
                self._go(State.ESCALATED, "G1 refused confirmation request -> M32")
                return
            self._go(State.AWAITING_CONFIRMATION, f"A9 C1-C7 pass -> G2 {level} -> G1 ok -> G3 request {ref}")

    # ----------------------------------------------------------------------- events
    def resume(self, event: dict) -> State:
        kind, sender = event["type"], event.get("from")
        if kind == "cancel" and self.state not in TERMINAL:
            self._go(State.CANCELLED, f"cancelled by {sender}")
            return self.state
        if kind == "mandate_changed" and self.state in WAITING:
            self._reset()
            self._go(State.LOADING_CONTEXT, "mandate changed -> reload and reframe (answers kept as history)")
            return self.run()
        if self.state == State.ESCALATED and kind == "owner_assigned":
            self._reset()
            self._go(State.LOADING_CONTEXT, "M32 assigned an owner -> restart from A1")
            return self.run()

        if self.state == State.AWAITING_OWNER and kind == "owner_reply":
            if sender not in self.outstanding["recipients"]:
                self._note(f"reply from {sender} ignored: not a person who was asked")
                return self.state
            answers, applied, pending, rejected = a6_record_answers(
                self.llm, self.outstanding, event["text"], sender, event["ref"], self.framing, self.authority)
            self.answers += answers
            self.resolved |= {a.gap_id for a in answers if a.resolves}
            for k, v in applied.items():
                setattr(self.framing, k, v)
            self.pending_mandate = sorted(set(self.pending_mandate) | set(pending))
            for r in rejected:
                self._note(f"A6 rejected update {r}")
            self._go(State.ASSESSING, f"A6 {len(answers)} answers from {sender}, resolved={sorted(self.resolved)}"
                                      + (f", pending mandate update={pending}" if pending else ""))
        elif self.state == State.AWAITING_OWNER and kind == "owner_timeout":
            self._go(State.ASSESSING, "no reply by deadline: silence is not permission, gaps stay open")
        elif self.state == State.AWAITING_CONFIRMATION and kind == "owner_confirm":
            decision_people = {self.authority.owner["person_id"]} | {d["person_id"] for d in self.authority.delegates}
            if sender not in decision_people:
                self._note(f"G3 refused: {sender} is not the owner or a delegate")
                return self.state
            if event.get("version") != self.brief.version:
                self._note("G3 refused: confirmation refers to another brief version")
                return self.state
            current = self.src.get_mandate(self.ctx.account["id"], (self.ctx.subscription or {}).get("id"))
            if (current or {}).get("version") != self.authority.mandate_version:
                self._reset()
                self._go(State.LOADING_CONTEXT, "G3: mandate changed since framing -> reframe")
                return self.run()
            self.brief.confirmed_by = sender
            final = State.QUALIFIED_COMPLETE if self.brief.status == "QUALIFIED" else State.COMPLETE
            if final == State.COMPLETE:
                self.brief.status = "CONFIRMED"
            self.publication = a10_publish(self.dossier, self.brief)
            req = self.authority.requester["person_id"]
            if req not in decision_people:
                self._send(req, "notify", "Your renewal request has been scoped",
                           f"Owner: {self.authority.owner['name']}. Question: {self.brief.decision_question}\n"
                           f"Exclusions: {'; '.join(self.brief.exclusions)}")
            self._go(final, f"G3 confirmed by {sender} -> A10 published {self.publication}")
            return self.state
        elif self.state == State.AWAITING_CONFIRMATION and kind == "owner_change_request":
            decision_people = {self.authority.owner["person_id"]} | {d["person_id"] for d in self.authority.delegates}
            if sender not in decision_people:
                self._note(f"change request from {sender} ignored: not owner or delegate")
                return self.state
            self.repairs = 0
            self.answers.append(Answer("OWNER-EDIT", event["text"], sender, event["ref"], True))
            if event.get("field") == "decision_question":
                self.framing.decision_question = event["value"]
                self._go(State.ASSEMBLING, "owner rewrote the decision question -> A8")
            else:
                self._go(State.DRAFTING_CRITERIA, "owner asked to change criteria/exclusions -> A7")
        elif self.state == State.AWAITING_CONFIRMATION and kind == "confirmation_timeout":
            self.reason = "owner did not confirm in time"
            self._go(State.ESCALATED, "brief NOT published; owner unavailable -> M32")
            return self.state
        else:
            raise ValueError(f"event {kind} is not valid in state {self.state.value}")
        return self.run()


# ============================================================================ demo fakes
class FakeSources:
    def __init__(self, data: dict):
        self.d = data

    def get_request(self, rid):
        return self.d["requests"].get(rid)

    def get_account(self, aid):
        return self.d["accounts"].get(aid)

    def list_subscriptions(self, aid):
        return self.d["subscriptions"]

    def list_documents(self, aid, sid):
        return [DocRef(**x, source=SourceRef("contract_repo", x["doc_id"])) for x in self.d["documents"]]

    def get_mandate(self, aid, sid):
        return self.d["mandate"]

    def get_current_brief(self, aid, sid):
        return self.d.get("current_brief")


class ScriptedLLM:
    """Stand-in for real LLM calls: returns the structured output a prompt would produce."""

    def __init__(self, script: dict):
        self.s = script

    def frame_request(self, text, context):
        return self.s["frame"]

    def parse_answers(self, questions, reply_text):
        return self.s["answers"].pop(0)

    def draft_criteria(self, framing, answers, authority):
        return self.s["criteria"]


class RecordingMessenger:
    def __init__(self):
        self.outbox: list[dict] = []

    def send(self, to, channel, subject, body):
        self.outbox.append({"to": to, "channel": channel, "subject": subject, "body": body})
        return f"MSG-{len(self.outbox):03d}"


class MemoryDossier:
    def __init__(self):
        self.entries: list[dict] = []

    def publish(self, section, payload):
        self.entries.append({"section": section, "payload": payload})
        return f"DOS-{len(self.entries):03d}"


def _docs():
    return [
        {"doc_id": "DOC-MSA-2024", "doc_type": "MSA", "version": "1.0", "status": "EXECUTED",
         "effective_date": "2024-07-01", "visibility": "SHARED"},
        {"doc_id": "DOC-OF-2024", "doc_type": "ORDER_FORM", "version": "1.0", "status": "EXECUTED",
         "effective_date": "2024-07-01", "visibility": "SHARED"},
        {"doc_id": "DOC-SLA-2024", "doc_type": "SLA", "version": "1.0", "status": "EXECUTED",
         "effective_date": "2024-07-01", "visibility": "SHARED"},
        {"doc_id": "DOC-AMD-1", "doc_type": "AMENDMENT", "version": "1.0", "status": "EXECUTED",
         "effective_date": "2025-02-01", "visibility": "SHARED"},
        {"doc_id": "DOC-Q-2027", "doc_type": "QUOTE", "version": "draft-2", "status": "DRAFT",
         "effective_date": "2026-11-01", "visibility": "SHARED"},
    ]


def _account():
    return {"id": "ACC-NW-001", "name": "Northwind Logistics", "our_side": "BUYER",
            "counterparty": "Westbrook Software"}


def _sub():
    return {"id": "SUB-CRM-01", "product": "Westbrook CRM Enterprise", "quantity": 150, "status": "ACTIVE",
            "term_start": "2024-07-01", "term_end": "2027-06-30", "sla_headline": "99.5% monthly uptime"}


def scenario_a():
    """Simple: clear request from the owner, analysis only, budget recorded."""
    data = {
        "requests": {"REQ-101": {"id": "REQ-101", "from_id": "U-PRIYA", "from_name": "Priya Shah",
                                 "from_role": "Head of Sales Operations",
                                 "text": "Our Westbrook CRM subscription ends on 30 June 2027. Please review "
                                         "whether we should renew and on what terms. Keep the annual cost under "
                                         "$130,000 and no disruption for the sales team. Analysis only for now."}},
        "accounts": {"ACC-NW-001": _account()}, "subscriptions": [_sub()], "documents": _docs(),
        "mandate": {"id": "MAN-77", "version": 3, "valid_until": "2027-06-30",
                    "owner": {"person_id": "U-PRIYA", "name": "Priya Shah", "role": "Head of Sales Operations",
                              "active": True},
                    "decision_rights": [{"person_id": "U-PRIYA", "name": "Priya Shah", "right": "recommend"},
                                        {"person_id": "U-CFO", "name": "CFO", "right": "approve > $100,000"}],
                    "allowed_actions": ["ANALYZE", "CONSULT_INTERNAL"],
                    "budget": {"amount": 130000, "currency": "USD", "period": "annual",
                               "source": {"system": "mandate_store", "ref": "MAN-77"}},
                    "deadline": None, "allowed_contact": ["INTERNAL"],
                    "approvers": [{"name": "CFO", "threshold": "> $100,000"}], "delegates": []},
    }
    llm = ScriptedLLM({
        "frame": {
            "desired_outcome": "Decide whether and on what terms to renew Westbrook CRM before 30 June 2027.",
            "decision_question": "Should Northwind renew Westbrook CRM when its term ends on 30 June 2027, "
                                 "and on what quantity, term and support terms within the approved budget?",
            "perspective": "BUYER", "requested_actions": ["ANALYZE"],
            "candidate_goals": [{"statement": "Annual cost under $130,000", "source": "REQ-101"},
                                {"statement": "No disruption for the sales team", "source": "REQ-101"}],
            "stated_dates": [], "decision_paths": ["RENEW", "RENEW_CHANGED"],
            "solution_signals": [], "priority_conflicts": [], "request_kind": "FULL_REVIEW"},
        "answers": [],
        "criteria": {"criteria": [
            {"id": "SC1", "statement": "Annual subscription cost stays below the approved ceiling",
             "priority": "MUST", "measure": "annual cost", "target": "< 130,000 USD",
             "source": {"system": "mandate_store", "ref": "MAN-77"}, "depends_on": ["M02", "M10"]},
            {"id": "SC2", "statement": "Sales team keeps uninterrupted CRM access through the renewal",
             "priority": "MUST", "measure": "service continuity", "target": "0 days without access",
             "source": {"system": "request", "ref": "REQ-101"}, "depends_on": ["M03"]},
            {"id": "SC3", "statement": "Licence count matches observed need",
             "priority": "SHOULD", "measure": "licensed users vs active users", "target": "within 5%",
             "source": {"system": "request", "ref": "REQ-101"}, "depends_on": ["M05"]}],
            "exclusions": ["No contact with Westbrook during this Review.", "No change to user accounts."]},
    })
    return {"account_id": "ACC-NW-001", "request_id": "REQ-101"}, data, llm


def scenario_b():
    """Complex: solution-phrased request from a non-owner, no budget, renew-or-replace, unclear priorities."""
    data = {
        "requests": {"REQ-202": {"id": "REQ-202", "from_id": "U-DAN", "from_name": "Daniel Okafor",
                                 "from_role": "VP Sales",
                                 "text": "Negotiate the Westbrook CRM renewal and get 15% off. Also push the SLA "
                                         "up to 99.95%. We might switch to a competitor if they won't agree. "
                                         "Need this decided by 31 March 2027."}},
        "accounts": {"ACC-NW-001": _account()}, "subscriptions": [_sub()], "documents": _docs(),
        "mandate": {"id": "MAN-78", "version": 1, "valid_until": "2027-06-30",
                    "owner": {"person_id": "U-MEI", "name": "Mei Lin", "role": "CIO", "active": True},
                    "decision_rights": [{"person_id": "U-MEI", "name": "Mei Lin", "right": "decide renewal strategy"}],
                    "allowed_actions": ["ANALYZE", "CONSULT_INTERNAL"],
                    "budget": None, "deadline": None, "allowed_contact": ["INTERNAL"],
                    "approvers": [{"name": "Finance (Tom Reyes)", "threshold": "budget ceiling"}],
                    "delegates": []},
    }
    llm = ScriptedLLM({
        "frame": {
            "desired_outcome": "Lower renewal cost and a stronger SLA, or a better alternative.",
            "decision_question": "Should Northwind renew Westbrook CRM on changed price and service terms, or "
                                 "replace it, and which terms should it seek within its authority?",
            "perspective": "BUYER", "requested_actions": ["ANALYZE", "NEGOTIATE", "CONTACT_COUNTERPARTY"],
            "candidate_goals": [{"statement": "15% lower price", "source": "REQ-202"},
                                {"statement": "SLA 99.95%", "source": "REQ-202"}],
            "stated_dates": [{"label": "Decision wanted by (VP Sales)", "date": "2027-03-31",
                              "kind": "INTERNAL_TARGET", "source": {"system": "request", "ref": "REQ-202"}}],
            "decision_paths": ["RENEW_CHANGED", "REPLACE"],
            "solution_signals": ["negotiate", "get 15% off"],
            "priority_conflicts": [{"text": "A 15% price cut and a higher SLA pull in opposite directions; "
                                            "the request does not say which is the must-have.",
                                    "between_stakeholders": False}],
            "request_kind": "FULL_REVIEW"},
        "answers": [
            {"answers": [
                {"gap_id": "G-AUTH-ACTIONS", "text": "Analysis only for now. No contact with Westbrook yet.",
                 "resolves": True},
                {"gap_id": "G-BUDGET", "text": "Finance (Tom Reyes) owns the budget ceiling; not set yet.",
                 "resolves": False},
                {"gap_id": "G-SCOPE-REPLACE", "text": "Yes, include replacement as an option.", "resolves": True}],
             "updates": {"requested_actions": ["ANALYZE"]}},
            {"answers": [
                {"gap_id": "G-PRIORITY-1", "text": "99.9% uptime is a must. 99.95% is nice to have. "
                                                   "15% is a target, not a must.", "resolves": True}],
             "updates": {"priority_conflicts": []}}],
        "criteria": {"criteria": [
            {"id": "SC1", "statement": "Uptime commitment of at least 99.9% in any renewed or replacement contract",
             "priority": "MUST", "measure": "uptime SLA", "target": ">= 99.9%",
             "source": {"system": "answer", "ref": "MSG-R2"}, "depends_on": ["M02", "M04"]},
            {"id": "SC2", "statement": "Uptime of 99.95% if available without breaking cost goals",
             "priority": "SHOULD", "measure": "uptime SLA (stretch)", "target": ">= 99.95%",
             "source": {"system": "request", "ref": "REQ-202"}, "depends_on": ["M04"]},
            {"id": "SC3", "statement": "Annual cost about 15% below the current contract", "priority": "SHOULD",
             "measure": "annual cost", "target": "-15% vs current baseline",
             "source": {"system": "answer", "ref": "MSG-R2"}, "depends_on": ["M02", "M10"]},
            {"id": "SC4", "statement": "Decision ready before the requester's target date", "priority": "SHOULD",
             "measure": "decision date", "target": "by 2027-03-31 (internal target)",
             "source": {"system": "request", "ref": "REQ-202"}, "depends_on": ["M03"]}],
            "exclusions": ["No supplier contact or negotiation during this Review (owner answer MSG-R1)."]},
    })
    return {"account_id": "ACC-NW-001", "subscription_id": "SUB-CRM-01", "request_id": "REQ-202"}, data, llm


def run_scenario_a():
    inputs, data, llm = scenario_a()
    msg, dos = RecordingMessenger(), MemoryDossier()
    run = M01Run(inputs, FakeSources(data), llm, msg, dos)
    run.run()
    run.resume({"type": "owner_confirm", "from": "U-PRIYA", "version": 1})
    return run, msg, dos


def run_scenario_b():
    inputs, data, llm = scenario_b()
    msg, dos = RecordingMessenger(), MemoryDossier()
    run = M01Run(inputs, FakeSources(data), llm, msg, dos)
    run.run()
    run.resume({"type": "owner_reply", "from": "U-MEI", "ref": "MSG-R1",
                "text": "1) Analysis only for now, no contact with Westbrook. 2) Budget is with Finance, "
                        "Tom hasn't set it. 3) Yes, include replacement."})
    run.resume({"type": "owner_reply", "from": "U-MEI", "ref": "MSG-R2",
                "text": "99.9% uptime is a must, 99.95 nice to have. 15% is a target, not a must."})
    run.resume({"type": "owner_confirm", "from": "U-DAN", "version": 1})    # wrong person: G3 refuses
    run.resume({"type": "owner_confirm", "from": "U-MEI", "version": 1})
    return run, msg, dos


def show(title, run, msg):
    print(f"\n{'=' * 100}\n{title}\n{'=' * 100}")
    print("\n".join(run.trace))
    print(f"\nFINAL STATE: {run.state.value}  {run.reason}")
    for m in msg.outbox:
        print(f"\n[message to {m['to']}] {m['subject']}\n{m['body']}")
    if run.brief:
        b = asdict(run.brief)
        keep = {k: b[k] for k in ("status", "confirmed_by", "decision_question", "authorized_actions",
                                  "exclusions", "unresolved_authority", "recommended_next_moves")}
        keep["success_criteria"] = [f'{c["priority"]}: {c["statement"]} [{c["target"]}]' for c in b["success_criteria"]]
        keep["open_questions"] = [f'{q["severity"]}: {q["description"]}' for q in b["open_questions"]]
        keep["dates"] = [f'{d["kind"]}: {d["label"]} = {d["date"]}' for d in b["dates"]]
        print("\nBRIEF:\n" + json.dumps(keep, indent=2))


if __name__ == "__main__":
    show("SCENARIO A - simple renewal review", *run_scenario_a()[:2])
    show("SCENARIO B - complex, solution-phrased request", *run_scenario_b()[:2])
