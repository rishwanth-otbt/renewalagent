"""Invalid-input samples must still be rejected (HTTP 422) before any analysis."""
import pytest
from fastapi.testclient import TestClient

import main
from tests.conftest import SAMPLES_DIR, load_json

INVALID = sorted(SAMPLES_DIR.glob("*rejected_422*.json"))


@pytest.mark.parametrize("path", INVALID, ids=lambda p: p.stem)
def test_invalid_sample_is_rejected(path):
    client = TestClient(main.app)
    r = client.post("/api/upload", json={"filename": path.name, "data": load_json(path)})
    assert r.status_code == 422
    assert client.get("/api/cases").json()["cases"] == []  # nothing was stored


def test_there_are_invalid_samples():
    assert len(INVALID) == 3
