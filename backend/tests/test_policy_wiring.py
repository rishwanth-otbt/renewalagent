"""run_play loads the current policy from the store when none is given and records it in the Dossier."""
from app.core.orchestrator import RenewalAgentOrchestrator
from app.core.policy_store import PolicyStore
from app.models.policy_models import RenewalPolicy
from tests.conftest import AS_OF, DATA_DIR, load_json

CASE = load_json(DATA_DIR / "renewal_input_001.json")


def test_run_uses_store_defaults_when_nothing_saved(tmp_path):
    store = PolicyStore(tmp_path)
    brief = RenewalAgentOrchestrator(store).run_play(CASE, as_of=AS_OF)["brief"]
    assert brief["meta"]["policy_version"] == 0


def test_run_uses_latest_saved_policy(tmp_path):
    store = PolicyStore(tmp_path)
    store.save(RenewalPolicy.model_validate({"switch": {"price_shock_pct": 20}}), saved_by="test")
    brief = RenewalAgentOrchestrator(store).run_play(CASE, as_of=AS_OF)["brief"]
    assert brief["meta"]["policy_version"] == 1


def test_explicit_policy_is_a_draft(tmp_path):
    brief = RenewalAgentOrchestrator(PolicyStore(tmp_path)).run_play(CASE, as_of=AS_OF, policy=RenewalPolicy())["brief"]
    assert brief["meta"]["policy_version"] is None
