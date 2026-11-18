# AI Agent & Developer Playbook: Working with Renewal Desk

## 1. Overview for Incoming Agents

Welcome! This repository implements an automated IT Vendor Renewal Intelligence Agent based on the **Kozmo Renewal Desk** architecture. It reads raw IT contract and usage JSON data, executes a directed graph of **Moves, Actions, and Gates**, and renders an executive one-page renewal decision brief in a web UI.

Before modifying code, read this guide and `KOZMO_MOVE_ARCHITECTURE.md`.

---

## 2. Codebase Organization

```
RenewalAgent/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   ├── base_move.py      # Base class: execute_action, skip_action, record_gate, trace models
│   │   │   ├── dossier.py        # Central typed repository holding extracted facts and final brief
│   │   │   └── orchestrator.py   # RenewalDeskOrchestrator: runs M01 -> M02 -> M03 -> M04 -> M05 -> M10
│   │   ├── models/
│   │   │   └── input_models.py   # Pydantic models for REST requests (Upload, Process)
│   │   └── moves/
│   │       ├── m01_goals.py       # Frame: Owner, decision question, budget ceiling
│   │       ├── m02_terms.py       # Research: Baseline terms, pricing structure, addenda audit
│   │       ├── m03_deadlines.py   # Verify: Notice cutoff, auto-renewal trap detection
│   │       ├── m04_performance.py # Evaluate: SLA availability, outage forensics, credits
│   │       ├── m05_licenses.py    # Analyze: Seat adoption, shelfware remediation
│   │       └── m10_recommend.py   # Model: Financial modeling, risk synthesis, strategic routing
│   ├── data/
│   │   ├── renewal_input_001.json # Scenario 1: Renegotiate (High risk, shelfware, outages)
│   │   ├── renewal_input_002.json # Scenario 2: Renew (Low risk, healthy adoption)
│   │   └── renewal_input_003.json # Scenario 3: Switch / Benchmark (Severe SLA breach)
│   └── main.py                    # FastAPI server & static file host (mounts frontend at root)
│
├── frontend/
│   ├── index.html                 # Executive Brief template + Move Flow Modal dialog
│   ├── style.css                  # Executive styling + Modal styling
│   └── app.js                     # Fetch API, render brief data, and populate Move Flow Modal
│
├── KOZMO_MOVE_ARCHITECTURE.md     # Full architectural specification of the Move Graph
├── AGENT_DEVELOPER_GUIDE.md       # This file: How to maintain, extend, and test the agent
└── README.md                      # High-level overview and quickstart
```

---

## 3. How to Add a New Move (Step-by-Step)

If you need to introduce a new move (for example, `M06 Benchmark Market Rates` or `M07 Model Redundancy Risks`):

### Step 1: Create the Move File
Create `backend/app/moves/m06_benchmark.py`:
```python
from typing import Any, Dict, List
try:
    from backend.app.core.base_move import BaseMove, MoveTrace
except ImportError:
    from app.core.base_move import BaseMove, MoveTrace

class MoveM06BenchmarkMarketRates(BaseMove):
    move_id = "M06"
    name = "Benchmark Market Rates"
    verb = "BENCHMARK"

    def run(self, dossier: Any) -> MoveTrace:
        self.action_traces = []
        self.gate_traces = []
        
        # 1. Gate: Check if market benchmark data is available
        market_data_available = bool(dossier.raw_data.get("market_benchmarks"))
        self.record_gate(
            gate_id="G1",
            name="MarketDataAvailableCheck",
            passed=market_data_available,
            decision="EXECUTE_BENCHMARK" if market_data_available else "SKIP_BENCHMARK",
            details="External peer pricing benchmark is available" if market_data_available else "No external benchmark data found in raw input"
        )

        # 2. Action: Run or skip based on Gate G1
        if market_data_available:
            self.execute_action("A1", "Compare Against Market Quartiles", lambda: self._do_benchmark(dossier))
        else:
            self.skip_action("A1", "Compare Against Market Quartiles", "No external peer pricing data present in intake dossier")

        return MoveTrace(
            move_id=self.move_id,
            name=self.name,
            verb=self.verb,
            status="COMPLETED",
            actions=self.action_traces,
            gates=self.gate_traces,
            summary="Market benchmarking completed."
        )

    def _do_benchmark(self, dossier: Any) -> str:
        # Business logic goes here
        return "Market rate is $140/seat vs proposed $175/seat"
```

### Step 2: Register Move in Orchestrator
In `backend/app/core/orchestrator.py`:
```python
# Import the new move with fallback
from backend.app.moves.m06_benchmark import MoveM06BenchmarkMarketRates

# Add it to self.moves in __init__:
self.moves = [
    MoveM01SetRenewalGoals(),
    MoveM02CheckAgreementTerms(),
    MoveM03CheckRenewalDeadlines(),
    MoveM04AssessSupplierPerformance(),
    MoveM05AnalyzeLicenseNeeds(),
    MoveM06BenchmarkMarketRates(), # <-- NEW
    MoveM10ModelCostsAndRecommend(),
]
```

### Step 3: Add to Frontend Move List (Optional)
In `frontend/app.js`:
Add `{ id: "M06", name: "M06 Benchmark" }` to `KOZMO_MOVES`. The UI modal automatically renders any move in `brief.meta.move_trace` dynamically!

---

## 4. How to Add an Action to an Existing Move

1. Always define the action logic in a private method (e.g. `_audit_security(dossier)`).
2. Before calling `self.execute_action(...)`, check if a **Gate condition** should control its execution.
3. If the condition is met, call:
   ```python
   self.execute_action("A_ID", "Human-Readable Name", lambda: self._my_logic(dossier), format_output=lambda res: f"Result: {res}")
   ```
4. If bypassed, call:
   ```python
   self.skip_action("A_ID", "Human-Readable Name", "Explain WHY it was skipped based on the gate")
   ```

---

## 5. Testing & Verification

### Run CLI Verification Across All 3 Scenarios
```powershell
python -c "import sys; sys.path.insert(0, '.'); from backend.app.core.orchestrator import RenewalDeskOrchestrator; import json; orch = RenewalDeskOrchestrator(); [print(c, orch.run_play(json.load(open('backend/data/'+c)))['brief']['meta']['decision']) for c in ['renewal_input_001.json','renewal_input_002.json','renewal_input_003.json']]"
```
**Expected Output:**
- `renewal_input_001.json` ➔ `Renegotiate`
- `renewal_input_002.json` ➔ `Renew`
- `renewal_input_003.json` ➔ `Switch / Benchmark`

### Run FastAPI Server
```powershell
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```
Open `http://localhost:8000` in the browser and test:
1. Switch between cases in the dropdown.
2. Click **`🔀 View Move Flow`** to verify all moves, gates, executed actions (green), and skipped actions (gray) appear properly.
3. Click **`🖨️ Export PDF`** to check the printable stylesheet.

---

## 6. Critical Implementation Rules

1. **Deterministic Rule Logic Only**: This POC does not use LLMs, network calls, or external databases. Keep all computations in clean, testable Python functions.
2. **Double Import Resolution Pattern**: Because the app can be run from the root directory or from inside `backend/`, all imports inside `app/` and `main.py` MUST use try-except fallback imports (`from backend.app...` except `from app...`).
3. **FastAPI Static Mount Order**: The root mount `app.mount("/", StaticFiles(...))` MUST be placed AFTER all `@app.get` and `@app.post` route definitions, otherwise it shadows the REST API.
4. **Section 7 Is Commented Out**: Section 7 ("Recommended Further Investigations") in `index.html` and `app.js` was commented out because estimated days were hardcoded. Keep it commented out until dynamic generation is implemented in a future phase.
5. **No Heavy Frontend Frameworks**: Do NOT add npm, React, Vue, webpack, or chart.js. The UI is built with zero-dependency native HTML5, CSS variables, and vanilla JavaScript.
