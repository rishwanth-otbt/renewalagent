# AI IT Vendor Renewal Intelligence Agent — POC 1

Proof of Concept 1 implementation of the automated IT Vendor Renewal Decision Brief system.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  LAYER 1 — INPUT (backend/data/*.json)                  │
│  Raw Contract Repository: MSA · SLA · Pricing · Seats · │
│  Addendum · Emails · History · Internal Assessment      │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 2 — STATE MACHINE (backend/state_machine.py)     │
│  IDLE → INTAKE → EXTRACT → COMPARE → CALCULATE →       │
│  ASSESS → RECOMMEND → BRIEF_READY                       │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────┐
│  LAYER 3 — EXECUTIVE BRIEF (FastAPI + HTML/CSS/JS)      │
│  Serves slim brief JSON to vanilla frontend.            │
│  No external chart dependencies. Native Print to PDF.   │
└─────────────────────────────────────────────────────────┘
```

## Quick Start Guide

### 1. Install Backend Dependencies
Ensure you have Python 3.10+ installed.

```bash
cd backend
pip install -r requirements.txt
```

### 2. Start FastAPI Server
```bash
python main.py
# Or: uvicorn main:app --reload --port 8000
```

### 3. Open the Application
Navigate to [http://localhost:8000](http://localhost:8000) in any web browser.

The FastAPI app automatically mounts and serves the `frontend/` directory directly at `/`, while exposing the REST endpoints:
- `GET /api/cases`: Lists available raw contract JSON files.
- `GET /api/case/{case_id}`: Executes the state machine and returns the brief JSON.
- `POST /api/process`: Processes a case on demand.
- `GET /health`: Health check endpoint.

You can also open `frontend/index.html` directly in your browser.

### 4. Adding New Test Contracts
Drop any new `.json` file conforming to the contract schema into `backend/data/`. Refresh the web interface, and it will immediately show up in the case selector dropdown for automated evaluation.
