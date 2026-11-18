import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

try:
    from backend.app.core.orchestrator import RenewalAgentOrchestrator, CaseValidationError, validate_case
    from backend.app.core.policy_store import default_store
    from backend.app.db import repository as repo
    from backend.app.db.database import session_scope
    from backend.app.models.input_models import PdfExportRequest, ProcessRequest, UploadCaseRequest
    # from backend.app.models.policy_models import RenewalPolicy, policy_field_catalog  # POLICY DISABLED
except ImportError:
    from app.core.orchestrator import RenewalAgentOrchestrator, CaseValidationError, validate_case
    from app.core.policy_store import default_store
    from app.db import repository as repo
    from app.db.database import session_scope
    from app.models.input_models import PdfExportRequest, ProcessRequest, UploadCaseRequest
    # from app.models.policy_models import RenewalPolicy, policy_field_catalog  # POLICY DISABLED

app = FastAPI(
    title="AI IT Vendor Renewal Intelligence Agent - POC 1",
    description="Automated move pipeline that ingests raw contract data and generates an executive renewal decision brief."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def no_stale_frontend(request, call_next):
    """Make the browser re-check frontend files on every load, so edits show up without a hard refresh."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# Versioned client policy (backend/policies/). Module-level so tests can swap in a temporary store.
POLICY_STORE = default_store()


def _orchestrator() -> RenewalAgentOrchestrator:
    return RenewalAgentOrchestrator(POLICY_STORE)


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    """Database down or misconfigured: say so plainly instead of a bare 500."""
    return JSONResponse(
        status_code=503,
        content={"detail": f"Database error ({type(exc).__name__}). Check that SQL Server is running and "
                           f"DATABASE_URL in backend/.env is correct."},
    )


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Renewal Intelligence Agent POC 1"}


def _clean_filename(filename: str) -> str:
    """The uploaded file's own name, without any folder part, trimmed to a sensible length."""
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    return name[:120]


def _load_contract_json(session, case_id: int):
    contract = repo.get_contract(session, case_id)
    if contract is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found.")
    return contract, json.loads(contract.contract_json)


def _run(case_id: int, raw_data: Dict[str, Any], as_of: date) -> Dict[str, Any]:
    try:
        result = _orchestrator().run_play(raw_data, as_of=as_of)
    except CaseValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Case '{case_id}' is missing required data or has invalid values: " + "; ".join(e.errors),
        )
    return jsonable_encoder(result["brief"])


@app.get("/api/cases")
def list_cases():
    """Lists the contracts stored in the database.

    `cases` is the list of ids. `items` pairs each id with the name to show the user;
    if two uploads share a name, later ones get " (2)", " (3)" so the list stays unambiguous.
    """
    with session_scope() as s:
        contracts = repo.list_contracts(s)
    items, seen = [], {}
    for c in contracts:
        name = c.display_name
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name} ({seen[name]})"
        items.append({"id": c.id, "name": name})
    return {"cases": [c.id for c in contracts], "items": items}


@app.get("/api/case/{case_id}")
def get_case_brief(case_id: int, as_of: Optional[date] = None):
    """Runs the move pipeline on a stored contract and returns the brief. Read-only: nothing is saved.

    as_of (YYYY-MM-DD, optional) fixes the assessment date so results are repeatable; defaults to today.
    """
    with session_scope() as s:
        _, raw_data = _load_contract_json(s, case_id)
    return _run(case_id, raw_data, as_of or date.today())


@app.post("/api/process")
def process_case(request: ProcessRequest):
    """'Generate brief': runs the pipeline, saves the result in EvaluationResults and returns the brief.

    The brief's meta gains result_id (needed to record a PDF export) and evaluated_at.
    """
    as_of = request.as_of or date.today()
    with session_scope() as s:
        contract, raw_data = _load_contract_json(s, request.case_id)
        brief = _run(request.case_id, raw_data, as_of)
        result = repo.add_result(s, contract, brief, as_of)
        brief["meta"]["result_id"] = result.id
        brief["meta"]["evaluated_at"] = result.evaluated_at.isoformat(sep=" ")
    return brief


@app.post("/api/upload")
def upload_case(req: UploadCaseRequest):
    """Validates contract JSON and saves it in the Contracts table; returns its id (ContractId)."""
    try:
        validate_case(req.data)
    except CaseValidationError as e:
        raise HTTPException(
            status_code=422,
            detail="Uploaded case is missing required data or has invalid values: " + "; ".join(e.errors),
        )

    uploaded_by = (req.uploaded_by or "").strip() or None
    display_name = _clean_filename(req.filename) or "Uploaded contract"
    data = dict(req.data)
    with session_scope() as s:
        contract = repo.add_contract(
            s,
            display_name=display_name,
            original_filename=(req.filename or "")[:260] or None,
            uploaded_by=uploaded_by,
            data=data,
        )
        # The brief shows the JSON's case_id; make it unique from the new ContractId.
        data["case_id"] = f"RENEWAL-{date.today().year}-{contract.id:03d}"
        repo.set_contract_json(contract, data)
    return {
        "message": "File uploaded successfully",
        "case_id": contract.id,
        "original_filename": req.filename,
        "display_name": display_name,
    }


@app.post("/api/exports")
def record_pdf_export(req: PdfExportRequest):
    """Records who exported which generated brief as PDF, and when (PdfExports table)."""
    exported_by = req.exported_by.strip()
    if not exported_by:
        raise HTTPException(status_code=422, detail="exported_by is required.")
    with session_scope() as s:
        result = repo.get_result(s, req.result_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Result {req.result_id} not found. Generate the brief again.")
        export = repo.add_export(s, result, exported_by)
    return {
        "export_id": export.id,
        "result_id": export.result_id,
        "exported_by": export.exported_by,
        "exported_at": export.exported_at.isoformat(sep=" "),
    }


# POLICY DISABLED for this version: policy API (get / save / history / preview) commented out.
# # ---------------------------------------------------------------------------
# # Policy: the client's renewal rules (M1)
# # ---------------------------------------------------------------------------
#
# class PolicySaveRequest(BaseModel):
#     policy: Dict[str, Any]
#     saved_by: str = Field(min_length=1)
#     note: Optional[str] = None
#
#
# class PolicyPreviewRequest(BaseModel):
#     policy: Dict[str, Any]
#     as_of: Optional[date] = None
#
#
# def _policy_errors(exc: ValidationError) -> List[str]:
#     out = []
#     for err in exc.errors():
#         loc = ".".join(str(p) for p in err["loc"])
#         msg = err["msg"].removeprefix("Value error, ")
#         out.append(f"{loc}: {msg}" if loc else msg)
#     return out
#
#
# def _parse_policy(data: Dict[str, Any]) -> RenewalPolicy:
#     try:
#         return RenewalPolicy.model_validate(data)
#     except ValidationError as exc:
#         raise HTTPException(status_code=422, detail={"message": "Policy is invalid", "errors": _policy_errors(exc)})
#
#
# @app.get("/api/policy")
# def get_policy():
#     """Current policy (latest saved version, or built-in defaults as version 0), plus defaults and field catalog."""
#     return {
#         "current": POLICY_STORE.load_current().to_dict(),
#         "defaults": RenewalPolicy().model_dump(),
#         "catalog": policy_field_catalog(),
#     }
#
#
# @app.put("/api/policy")
# def save_policy(req: PolicySaveRequest):
#     """Validate and save the policy as the next version. 422 with a list of problems if invalid."""
#     policy = _parse_policy(req.policy)
#     stored = POLICY_STORE.save(policy, saved_by=req.saved_by, note=req.note)
#     return stored.to_dict()
#
#
# @app.get("/api/policy/history")
# def policy_history():
#     """All saved versions, newest first."""
#     return {"versions": [s.to_dict() for s in POLICY_STORE.history()]}
#
#
# def _summary(brief: Dict[str, Any]) -> Dict[str, Any]:
#     return {
#         "decision": brief["recommendation"]["primary"],
#         "risk_level": brief["risks"]["overall_level"],
#         "negotiation_target_acv": brief["financials"]["negotiation_target_acv"],
#         "performance_rating": brief["performance"]["overall_rating"],
#         "notice_status": brief["meta"]["notice_status"],
#         "decided_by": brief["meta"]["decided_by"],
#     }
#
#
# @app.post("/api/policy/preview")
# def preview_policy(req: PolicyPreviewRequest):
#     """Run every stored case with the current policy and with a draft policy; nothing is saved."""
#     draft = _parse_policy(req.policy)
#     current = POLICY_STORE.load_current()
#     as_of = req.as_of or date.today()
#     orch = _orchestrator()
#     rows = []
#     for path in sorted(DATA_DIR.glob("*.json")):
#         try:
#             with open(path, "r", encoding="utf-8") as f:
#                 raw = json.load(f)
#             now = orch.run_play(raw, as_of=as_of, policy=current.policy, policy_version=current.version)["brief"]
#             new = orch.run_play(raw, as_of=as_of, policy=draft)["brief"]
#         except (CaseValidationError, ValueError, OSError) as e:
#             rows.append({"case_id": path.stem, "error": str(e)})
#             continue
#         a, b = _summary(now), _summary(new)
#         rows.append({
#             "case_id": path.stem,
#             "vendor": now["vendor"]["name"],
#             "current": a,
#             "draft": b,
#             "decision_changed": a["decision"] != b["decision"],
#             "changed_fields": [k for k in a if k != "decided_by" and a[k] != b[k]],
#         })
#     return {
#         "as_of": as_of.isoformat(),
#         "current_version": current.version,
#         "cases": rows,
#         "decisions_changed": sum(1 for r in rows if r.get("decision_changed")),
#     }


# Mount frontend at root so index.html, style.css, and app.js are all served correctly
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
