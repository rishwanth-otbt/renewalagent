"""
Orchestrator: Executes the Kozmo Renewal Capability Play.
Runs the Move Graph pipeline: M01 -> M02 -> M03 -> M04 -> M05 -> M10
Collects execution traces and outputs both the Executive Brief and Move Trace.

The raw case is validated against RenewalInputData BEFORE any move runs.
Moves therefore read required fields directly (raw["msa"]["current_term_end"])
and never substitute default values for missing data.
"""
from dataclasses import asdict
from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

try:
    from backend.app.core.dossier import Dossier
    from backend.app.core.base_move import MoveTrace
    from backend.app.models.input_models import RenewalInputData
    from backend.app.moves.m01_goals import MoveM01SetRenewalGoals
    from backend.app.moves.m02_terms import MoveM02CheckAgreementTerms
    from backend.app.moves.m03_deadlines import MoveM03CheckRenewalDeadlines
    from backend.app.moves.m04_performance import MoveM04AssessSupplierPerformance
    from backend.app.moves.m05_licenses import MoveM05AnalyzeLicenseNeeds
    from backend.app.moves.m10_recommend import MoveM10ModelCostsAndRecommend
except ImportError:
    from app.core.dossier import Dossier
    from app.core.base_move import MoveTrace
    from app.models.input_models import RenewalInputData
    from app.moves.m01_goals import MoveM01SetRenewalGoals
    from app.moves.m02_terms import MoveM02CheckAgreementTerms
    from app.moves.m03_deadlines import MoveM03CheckRenewalDeadlines
    from app.moves.m04_performance import MoveM04AssessSupplierPerformance
    from app.moves.m05_licenses import MoveM05AnalyzeLicenseNeeds
    from app.moves.m10_recommend import MoveM10ModelCostsAndRecommend


class CaseValidationError(Exception):
    """Raised when a case file is missing required data or has wrongly-typed values."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("Case data is incomplete or invalid: " + "; ".join(errors))


def format_validation_errors(exc: ValidationError) -> List[str]:
    out = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(root)"
        out.append(f"{loc}: {err['msg']}")
    return out


def validate_case(raw_json: Dict[str, Any]) -> RenewalInputData:
    try:
        return RenewalInputData.model_validate(raw_json)
    except ValidationError as exc:
        raise CaseValidationError(format_validation_errors(exc)) from exc


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

    def run_play(self, raw_json: Dict[str, Any], as_of: Optional[date] = None) -> Dict[str, Any]:
        """as_of is the assessment date; it defaults to today and can be fixed for repeatable runs/tests."""
        case = validate_case(raw_json)
        dossier = Dossier(
            raw_data=case.model_dump(by_alias=True),
            as_of=as_of or date.today(),
        )
        traces: List[Dict[str, Any]] = []

        for move in self.moves:
            trace: MoveTrace = move.run(dossier)
            traces.append(asdict(trace))

        dossier.brief["meta"]["move_trace"] = traces

        return {
            "brief": dossier.brief,
            "move_trace": traces
        }
