import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, ValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

try:
    from backend.app.core.orchestrator import RenewalDeskOrchestrator, CaseValidationError, validate_case
    from backend.app.core.policy_store import default_store
    from backend.app.models.input_models import ProcessRequest, UploadCaseRequest
    # from backend.app.models.policy_models import RenewalPolicy, policy_field_catalog  # POLICY DISABLED
except ImportError:
    from app.core.orchestrator import RenewalDeskOrchestrator, CaseValidationError, validate_case
    from app.core.policy_store import default_store
    from app.models.input_models import ProcessRequest, UploadCaseRequest
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
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR.parent / "frontend"

# Versioned client policy (backend/policies/). Module-level so tests can swap in a temporary store.
POLICY_STORE = default_store()


def _orchestrator() -> RenewalDeskOrchestrator:
    return RenewalDeskOrchestrator(POLICY_STORE)


def _case_path(case_id: str) -> Path:
    """Resolve a case id to a JSON file inside DATA_DIR; reject anything that escapes it."""
    stem = Path(case_id).stem if case_id.endswith(".json") else case_id
    path = (DATA_DIR / f"{stem}.json").resolve()
    if path.parent != DATA_DIR.resolve():
        raise HTTPException(status_code=400, detail="Invalid case id.")
    return path


CASE_PREFIX = "renewal_input_"
_CASE_NUM_RE = re.compile(rf"^{CASE_PREFIX}(\d+)$")


def _next_case_number() -> int:
    """Highest existing renewal_input_NNN number in DATA_DIR + 1 (001 if none)."""
    nums = [int(m.group(1)) for f in DATA_DIR.glob("*.json") if (m := _CASE_NUM_RE.match(f.stem))]
    return max(nums, default=0) + 1


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Renewal Intelligence Agent POC 1"}


# Uploaded files keep a safe internal id (renewal_input_NNN) but are shown under the name the user uploaded.
DISPLAY_NAME_KEY = "_display_name"


def _clean_filename(filename: str) -> str:
    """The uploaded file's own name, without any folder part, trimmed to a sensible length."""
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    return name[:120]


def _display_name(path: Path) -> str:
    """Original upload name if recorded, else a readable form of the id (renewal_input_001 -> Renewal Input 001)."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            name = json.load(f).get(DISPLAY_NAME_KEY)
        if isinstance(name, str) and name.strip():
            return name.strip()
    except (OSError, ValueError, AttributeError):
        pass
    return path.stem.replace("_", " ").title()


@app.get("/api/cases")
def list_cases():
    """Lists available case files in data folder.

    `cases` is the list of ids (unchanged). `items` pairs each id with the name to show the user;
    if two uploads share a name, later ones get " (2)", " (3)" so the list stays unambiguous.
    """
    if not DATA_DIR.exists():
        return {"cases": [], "items": []}
    paths = sorted(DATA_DIR.glob("*.json"), key=lambda p: p.stem)
    items, seen = [], {}
    for p in paths:
        name = _display_name(p)
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name} ({seen[name]})"
        items.append({"id": p.stem, "name": name})
    return {"cases": [p.stem for p in paths], "items": items}


@app.get("/api/case/{case_id}")
def get_case_brief(case_id: str, as_of: Optional[date] = None):
    """Loads raw contract JSON for case_id, executes the move pipeline, and returns the executive brief JSON.

    as_of (YYYY-MM-DD, optional) fixes the assessment date so results are repeatable; defaults to today.
    """
    json_path = _case_path(case_id)
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"Case file '{case_id}' not found in data directory.")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading JSON file: {str(e)}")

    try:
        result = _orchestrator().run_play(raw_data, as_of=as_of)
    except CaseValidationError as e:
        raise HTTPException(
            status_code=422,
            detail=f"Case '{case_id}' is missing required data or has invalid values: " + "; ".join(e.errors),
        )
    return result["brief"]


@app.post("/api/process")
def process_case(request: ProcessRequest):
    """Processes a case by ID via POST and returns the generated executive brief"""
    return get_case_brief(request.case_id)


@app.post("/api/upload")
def upload_case(req: UploadCaseRequest):
    """Validates custom contract JSON, saves it to the data directory, and returns its case_id"""
    try:
        validate_case(req.data)
    except CaseValidationError as e:
        raise HTTPException(
            status_code=422,
            detail="Uploaded case is missing required data or has invalid values: " + "; ".join(e.errors),
        )

    # Assign the next sequential id (renewal_input_004, 005, ...) regardless of the uploaded filename,
    # so uploads never overwrite an existing case and always follow the data folder's naming.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    seq = _next_case_number()
    case_stem = f"{CASE_PREFIX}{seq:03d}"
    save_path = _case_path(case_stem)

    data = dict(req.data)
    data["case_id"] = f"RENEWAL-{date.today().year}-{seq:03d}"
    display_name = _clean_filename(req.filename) or case_stem
    data[DISPLAY_NAME_KEY] = display_name
    try:
        # "x" mode fails instead of overwriting if the file somehow already exists
        with open(save_path, "x", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except FileExistsError:
        raise HTTPException(status_code=409, detail=f"Case '{case_stem}' already exists; please retry.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    return {
        "message": "File uploaded successfully",
        "case_id": case_stem,
        "renewal_id": data["case_id"],
        "original_filename": req.filename,
        "display_name": display_name,
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
