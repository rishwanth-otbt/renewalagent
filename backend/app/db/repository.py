"""Data access for contracts, evaluation results and PDF exports. Callers own the session/transaction."""
import json
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

try:
    from backend.app.db.models import Contract, EvaluationResult, PdfExport
except ImportError:
    from app.db.models import Contract, EvaluationResult, PdfExport


# ---------------------------------------------------------------- contracts

def list_contracts(session: Session) -> List[Contract]:
    return list(session.scalars(select(Contract).order_by(Contract.id)))


def get_contract(session: Session, contract_id: int) -> Optional[Contract]:
    return session.get(Contract, contract_id)


def add_contract(
    session: Session,
    *,
    display_name: str,
    data: Dict[str, Any],
    original_filename: Optional[str] = None,
    uploaded_by: Optional[str] = None,
) -> Contract:
    vendor = data.get("vendor") if isinstance(data.get("vendor"), dict) else {}
    contract = Contract(
        display_name=display_name,
        original_filename=original_filename,
        vendor_name=vendor.get("name"),
        contract_json=json.dumps(data, ensure_ascii=False),
        uploaded_by=uploaded_by,
    )
    session.add(contract)
    session.flush()  # assigns ContractId
    return contract


def set_contract_json(contract: Contract, data: Dict[str, Any]) -> None:
    contract.contract_json = json.dumps(data, ensure_ascii=False)


# ---------------------------------------------------------------- results

def add_result(session: Session, contract: Contract, brief: Dict[str, Any], as_of: date) -> EvaluationResult:
    """Store a generated brief. `brief` must already be JSON-safe."""
    result = EvaluationResult(
        contract_id=contract.id,
        as_of_date=as_of,
        decision=(brief.get("recommendation") or {}).get("primary"),
        risk_level=(brief.get("risks") or {}).get("overall_level"),
        policy_version=(brief.get("meta") or {}).get("policy_version"),
        result_json=json.dumps(brief, ensure_ascii=False),
    )
    session.add(result)
    session.flush()
    return result


def get_result(session: Session, result_id: int) -> Optional[EvaluationResult]:
    return session.get(EvaluationResult, result_id)


# ---------------------------------------------------------------- PDF exports

def add_export(session: Session, result: EvaluationResult, exported_by: str) -> PdfExport:
    export = PdfExport(contract_id=result.contract_id, result_id=result.id, exported_by=exported_by)
    session.add(export)
    session.flush()
    return export
