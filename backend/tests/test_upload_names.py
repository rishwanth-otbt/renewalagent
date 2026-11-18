"""Uploads are listed under the name the user uploaded, not the internal renewal_input_NNN id."""
import json
from pathlib import Path

from fastapi.testclient import TestClient

import main

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "renewal_input_001.json"


def _client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "renewal_input_001.json").write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(main, "DATA_DIR", data_dir)
    return TestClient(main.app), data_dir


def test_upload_keeps_original_name_for_display(tmp_path, monkeypatch):
    client, data_dir = _client(tmp_path, monkeypatch)
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))

    r = client.post("/api/upload", json={"filename": "Acme CRM contract.json", "data": payload})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["case_id"] == "renewal_input_002"          # safe internal id is unchanged
    assert body["display_name"] == "Acme CRM contract.json"

    listing = client.get("/api/cases").json()
    assert listing["cases"] == ["renewal_input_001", "renewal_input_002"]
    assert listing["items"] == [
        {"id": "renewal_input_001", "name": "Renewal Input 001"},
        {"id": "renewal_input_002", "name": "Acme CRM contract.json"},
    ]
    # The uploaded case still evaluates normally.
    assert client.get("/api/case/renewal_input_002").status_code == 200


def test_same_name_uploaded_twice_is_told_apart(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    for _ in range(2):
        assert client.post("/api/upload", json={"filename": "acme.json", "data": payload}).status_code == 200

    names = [i["name"] for i in client.get("/api/cases").json()["items"]]
    assert names == ["Renewal Input 001", "acme.json", "acme.json (2)"]


def test_folder_part_of_filename_is_dropped(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    payload = json.loads(SAMPLE.read_text(encoding="utf-8"))
    r = client.post("/api/upload", json={"filename": "C:\\Users\\me\\Desktop\\vendor.json", "data": payload})
    assert r.json()["display_name"] == "vendor.json"
