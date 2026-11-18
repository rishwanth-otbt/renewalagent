"""Uploads are listed under the name the user uploaded; the id is the ContractId."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

import main
from app.db import repository as repo
from app.db.database import session_scope

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "renewal_input_001.json"


def _client():
    """Database starts with renewal_input_001, imported the way the import script does it."""
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    with session_scope() as s:
        repo.add_contract(s, display_name="Renewal Input 001", data=data)
    return TestClient(main.app)


def _payload():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_upload_keeps_original_name_for_display():
    client = _client()
    r = client.post("/api/upload", json={"filename": "Acme CRM contract.json", "data": _payload()})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["case_id"] == 2                             # internal id = ContractId
    assert body["display_name"] == "Acme CRM contract.json"

    listing = client.get("/api/cases").json()
    assert listing["cases"] == [1, 2]
    assert listing["items"] == [
        {"id": 1, "name": "Renewal Input 001"},
        {"id": 2, "name": "Acme CRM contract.json"},
    ]
    # The uploaded case still evaluates normally.
    assert client.get("/api/case/2").status_code == 200


def test_same_name_uploaded_twice_is_told_apart():
    client = _client()
    for _ in range(2):
        assert client.post("/api/upload", json={"filename": "acme.json", "data": _payload()}).status_code == 200

    names = [i["name"] for i in client.get("/api/cases").json()["items"]]
    assert names == ["Renewal Input 001", "acme.json", "acme.json (2)"]


def test_folder_part_of_filename_is_dropped():
    client = _client()
    r = client.post("/api/upload", json={"filename": "C:\\Users\\me\\Desktop\\vendor.json", "data": _payload()})
    assert r.json()["display_name"] == "vendor.json"
