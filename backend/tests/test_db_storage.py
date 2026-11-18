"""Contracts, evaluation results and PDF exports are stored in the database."""
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

import main
from app.db.database import session_scope
from app.db.models import Contract, EvaluationResult, PdfExport

SAMPLE = Path(__file__).resolve().parents[0] / "fixtures" / "renewal_input_001.json"


def _upload(client, filename="Acme CRM.json", uploaded_by=None):
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    r = client.post("/api/upload", json={"filename": filename, "data": payload, "uploaded_by": uploaded_by})
    assert r.status_code == 200, r.text
    return r.json()["case_id"]


def test_upload_stores_contract_json_and_file_name():
    client = TestClient(main.app)
    case_id = _upload(client, filename="C:\\docs\\Acme CRM.json", uploaded_by="  Ravi ")
    with session_scope() as s:
        c = s.get(Contract, case_id)
        assert c.display_name == "Acme CRM.json"
        assert c.original_filename == "C:\\docs\\Acme CRM.json"
        assert c.uploaded_by == "Ravi"
        assert c.vendor_name == json.loads(SAMPLE.read_text(encoding="utf-8"))["vendor"]["name"]
        assert c.uploaded_at is not None
        stored = json.loads(c.contract_json)
        assert stored["case_id"] == f"RENEWAL-{c.uploaded_at.year}-{c.id:03d}"  # unique per contract
        assert "_display_name" not in stored


def test_generate_saves_a_result_and_view_does_not():
    client = TestClient(main.app)
    case_id = _upload(client)

    assert client.get(f"/api/case/{case_id}?as_of=2026-11-18").status_code == 200
    with session_scope() as s:
        assert s.scalars(select(EvaluationResult)).all() == []

    r = client.post("/api/process", json={"case_id": case_id, "as_of": "2026-11-18"})
    assert r.status_code == 200, r.text
    brief = r.json()
    with session_scope() as s:
        res = s.get(EvaluationResult, brief["meta"]["result_id"])
        assert str(res.as_of_date) == "2026-11-18"
        assert res.decision == brief["recommendation"]["primary"]
        assert res.risk_level == brief["risks"]["overall_level"]
        assert json.loads(res.result_json)["recommendation"] == brief["recommendation"]
    assert brief["meta"]["evaluated_at"]


def test_pdf_export_records_name_and_time():
    client = TestClient(main.app)
    case_id = _upload(client)
    result_id = client.post("/api/process", json={"case_id": case_id}).json()["meta"]["result_id"]

    r = client.post("/api/exports", json={"result_id": result_id, "exported_by": " Ravi "})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["exported_by"] == "Ravi" and body["exported_at"]
    with session_scope() as s:
        exp = s.get(PdfExport, body["export_id"])
        assert exp.result_id == result_id and exp.exported_by == "Ravi"


def test_pdf_export_needs_a_name_and_a_real_result():
    client = TestClient(main.app)
    assert client.post("/api/exports", json={"result_id": 999, "exported_by": "Ravi"}).status_code == 404
    assert client.post("/api/exports", json={"result_id": 1, "exported_by": ""}).status_code == 422
    assert client.post("/api/exports", json={"result_id": 1, "exported_by": "   "}).status_code == 422


def test_unknown_case_is_404():
    client = TestClient(main.app)
    assert client.get("/api/case/999").status_code == 404
    assert client.post("/api/process", json={"case_id": 999}).status_code == 404
