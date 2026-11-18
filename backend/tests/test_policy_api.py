"""Policy API: read, save (422 on invalid), history, preview; case runs use the saved policy."""
import pytest
from fastapi.testclient import TestClient

import main
from app.core.policy_store import PolicyStore
from app.models.policy_models import RenewalPolicy


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "POLICY_STORE", PolicyStore(tmp_path / "policies"))
    return TestClient(main.app)


def _policy(**changes):
    p = RenewalPolicy().model_dump()
    for path, value in changes.items():
        group, key = path.split("__")
        p[group][key] = value
    return p


def test_get_policy_returns_defaults_and_catalog(client):
    body = client.get("/api/policy").json()
    assert body["current"]["version"] == 0 and body["current"]["is_default"]
    assert body["current"]["policy"] == body["defaults"] == RenewalPolicy().model_dump()
    assert [g["key"] for g in body["catalog"]][:2] == ["renew", "switch"]


def test_put_saves_new_version_and_history(client):
    r = client.put("/api/policy", json={"policy": _policy(renew__max_increase_pct=7), "saved_by": "alice"})
    assert r.status_code == 200 and r.json()["version"] == 1
    client.put("/api/policy", json={"policy": _policy(renew__max_increase_pct=8), "saved_by": "bob", "note": "tighter"})
    assert client.get("/api/policy").json()["current"]["version"] == 2
    hist = client.get("/api/policy/history").json()["versions"]
    assert [(v["version"], v["saved_by"]) for v in hist] == [(2, "bob"), (1, "alice")]


def test_put_invalid_policy_is_422_with_clear_messages(client):
    r = client.put("/api/policy", json={"policy": _policy(renew__max_increase_pct=40), "saved_by": "alice"})
    assert r.status_code == 422
    errors = r.json()["detail"]["errors"]
    assert any("renew limit (40.0%) must be below the switch trigger (30.0%)" in e for e in errors)
    assert client.get("/api/policy").json()["current"]["version"] == 0


def test_put_requires_saved_by(client):
    assert client.put("/api/policy", json={"policy": _policy(), "saved_by": ""}).status_code == 422


def test_case_run_uses_saved_policy(client):
    as_of = "2026-11-18"
    before = client.get(f"/api/case/renewal_input_001?as_of={as_of}").json()
    assert before["recommendation"]["primary"] == "Renegotiate" and before["meta"]["policy_version"] == 0
    client.put("/api/policy", json={"policy": _policy(switch__price_shock_pct=20), "saved_by": "alice"})
    after = client.get(f"/api/case/renewal_input_001?as_of={as_of}").json()
    assert after["recommendation"]["primary"] == "Switch / Benchmark" and after["meta"]["policy_version"] == 1


def test_preview_runs_all_cases_without_saving(client):
    r = client.post("/api/policy/preview", json={"policy": _policy(switch__price_shock_pct=20), "as_of": "2026-11-18"})
    assert r.status_code == 200
    body = r.json()
    rows = {c["case_id"]: c for c in body["cases"]}
    assert rows["renewal_input_001"]["decision_changed"]
    assert rows["renewal_input_001"]["draft"]["decision"] == "Switch / Benchmark"
    assert body["decisions_changed"] >= 1
    assert client.get("/api/policy").json()["current"]["version"] == 0


def test_preview_invalid_policy_is_422(client):
    r = client.post("/api/policy/preview", json={"policy": _policy(performance__poor_support_sla_pct=95)})
    assert r.status_code == 422
