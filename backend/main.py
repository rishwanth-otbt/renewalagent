import os
import json
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

try:
    from backend.app.core.orchestrator import RenewalDeskOrchestrator
    from backend.app.models.input_models import ProcessRequest, UploadCaseRequest
except ImportError:
    try:
        from app.core.orchestrator import RenewalDeskOrchestrator
        from app.models.input_models import ProcessRequest, UploadCaseRequest
    except ImportError:
        RenewalDeskOrchestrator = None
        try:
            from backend.state_machine import RenewalStateMachine
            from backend.models import ProcessRequest, UploadCaseRequest
        except ImportError:
            from state_machine import RenewalStateMachine
            from models import ProcessRequest, UploadCaseRequest

app = FastAPI(
    title="AI IT Vendor Renewal Intelligence Agent - POC 1",
    description="Automated state machine that ingests raw contract data and generates an executive renewal decision brief."
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
def get_case_brief(case_id: str):
    """Loads raw contract JSON for case_id, executes state machine, and returns executive brief JSON"""
    json_path = DATA_DIR / f"{case_id}.json"
    if not json_path.exists():
        # check if case_id itself has .json or is just the stem
        json_path = DATA_DIR / case_id
        if not json_path.exists():
            raise HTTPException(status_code=404, detail=f"Case file '{case_id}' not found in data directory.")

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading JSON file: {str(e)}")

    if RenewalDeskOrchestrator:
        orch = RenewalDeskOrchestrator()
        result = orch.run_play(raw_data)
        return result["brief"]
    else:
        sm = RenewalStateMachine()
        brief = sm.run(raw_data)
        if brief.get("error"):
            raise HTTPException(status_code=422, detail=brief.get("message"))
        return brief

@app.post("/api/process")
def process_case(request: ProcessRequest):
    """Processes a case by ID via POST and returns the generated executive brief"""
    return get_case_brief(request.case_id)

@app.post("/api/upload")
def upload_case(req: UploadCaseRequest):
    """Receives custom contract JSON, saves it to data directory, and returns its case_id"""
    case_stem = Path(req.filename).stem
    save_path = DATA_DIR / f"{case_stem}.json"
    try:
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(req.data, f, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
    return {"message": "File uploaded successfully", "case_id": case_stem}

# Mount frontend at root so index.html, style.css, and app.js are all served correctly
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
