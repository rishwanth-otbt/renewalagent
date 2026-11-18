"""
Orchestrator: Executes the Kozmo Renewal Capability Play.
Runs the Move Graph pipeline: M01 -> M02 -> M03 -> M04 -> M05 -> M10
Collects execution traces and outputs both the Executive Brief and Move Trace.
"""
from dataclasses import asdict
from typing import Any, Dict, List, Tuple

try:
    from backend.app.core.dossier import Dossier
    from backend.app.core.base_move import MoveTrace
    from backend.app.moves.m01_goals import MoveM01SetRenewalGoals
    from backend.app.moves.m02_terms import MoveM02CheckAgreementTerms
    from backend.app.moves.m03_deadlines import MoveM03CheckRenewalDeadlines
    from backend.app.moves.m04_performance import MoveM04AssessSupplierPerformance
    from backend.app.moves.m05_licenses import MoveM05AnalyzeLicenseNeeds
    from backend.app.moves.m10_recommend import MoveM10ModelCostsAndRecommend
except ImportError:
    from app.core.dossier import Dossier
    from app.core.base_move import MoveTrace
    from app.moves.m01_goals import MoveM01SetRenewalGoals
    from app.moves.m02_terms import MoveM02CheckAgreementTerms
    from app.moves.m03_deadlines import MoveM03CheckRenewalDeadlines
    from app.moves.m04_performance import MoveM04AssessSupplierPerformance
    from app.moves.m05_licenses import MoveM05AnalyzeLicenseNeeds
    from app.moves.m10_recommend import MoveM10ModelCostsAndRecommend


class RenewalDeskOrchestrator:
    def __init__(self):
        self.moves = [
            MoveM01SetRenewalGoals(),
            MoveM02CheckAgreementTerms(),
            MoveM03CheckRenewalDeadlines(),
            MoveM04AssessSupplierPerformance(),
            MoveM05AnalyzeLicenseNeeds(),
            MoveM10ModelCostsAndRecommend(),
        ]

    def run_play(self, raw_json: Dict[str, Any]) -> Dict[str, Any]:
        dossier = Dossier(raw_data=raw_json)
        traces: List[Dict[str, Any]] = []

        for move in self.moves:
            trace: MoveTrace = move.run(dossier)
            traces.append(asdict(trace))

        # Add move_trace to brief.meta so it is accessible everywhere
        if "meta" in dossier.brief:
            dossier.brief["meta"]["move_trace"] = traces

        return {
            "brief": dossier.brief,
            "move_trace": traces
        }
