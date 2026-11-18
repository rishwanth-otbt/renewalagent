"""Policy store: defaults when empty, append-only versions, history, validation on save."""
import json

import pytest
from pydantic import ValidationError

from app.core.policy_store import PolicyStore
from app.models.policy_models import RenewalPolicy


@pytest.fixture
def store(tmp_path):
    return PolicyStore(tmp_path / "policies")


def test_empty_store_returns_defaults_as_version_0(store):
    current = store.load_current()
    assert current.version == 0 and current.is_default
    assert current.policy == RenewalPolicy()
    assert store.history() == []


def test_save_creates_next_version_and_keeps_history(store):
    p1 = RenewalPolicy.model_validate({"renew": {"max_increase_pct": 7}})
    p2 = RenewalPolicy.model_validate({"renew": {"max_increase_pct": 8}})
    s1 = store.save(p1, saved_by="alice", note="first")
    s2 = store.save(p2, saved_by="bob")
    assert (s1.version, s2.version) == (1, 2)
    current = store.load_current()
    assert current.version == 2 and current.saved_by == "bob"
    assert current.policy.renew.max_increase_pct == 8.0
    assert [h.version for h in store.history()] == [2, 1]
    assert store.load(1).policy.renew.max_increase_pct == 7.0
    assert store.load(1).note == "first"
    assert sorted(f.name for f in store.directory.iterdir()) == ["policy_v001.json", "policy_v002.json"]


def test_save_rejects_invalid_policy_and_writes_nothing(store):
    with pytest.raises(ValidationError):
        store.save({"renew": {"max_increase_pct": 50}}, saved_by="alice")
    assert store.load_current().version == 0


def test_save_requires_saved_by(store):
    with pytest.raises(ValueError):
        store.save(RenewalPolicy(), saved_by="  ")


def test_unknown_version_raises(store):
    with pytest.raises(KeyError):
        store.load(5)


def test_saved_file_is_plain_json(store):
    store.save(RenewalPolicy(), saved_by="alice")
    data = json.loads((store.directory / "policy_v001.json").read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["saved_by"] == "alice" and "renew" in data["policy"]
