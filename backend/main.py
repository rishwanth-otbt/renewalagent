import json
import re
from datetime import date
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

try:
    from backend.app.core.orchestrator import RenewalDeskOrchestrator, CaseValidationError, validate_case
    from backend.app.models.input_models import ProcessRequest, UploadCaseRequest
except ImportError:
    from app.core.orchestrator import RenewalDeskOrchestrator, CaseValidationError, validate_case
    from app.models.input_models import ProcessRequest, UploadCaseRequest

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

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR.parent / "frontend"


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


@app.get("/api/cases")
def list_cases():
    """Lists available case files in data folder"""
    if not DATA_DIR.exists():
        return {"cases": []}
    files = [f.stem for f in DATA_DIR.glob("*.json")]
    return {"cases": sorted(files)}


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
        result = RenewalDeskOrchestrator().run_play(raw_data, as_of=as_of)
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
    }


# Mount frontend at root so index.html, style.css, and app.js are all served correctly
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
