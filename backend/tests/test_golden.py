"""Golden tests: the default policy must reproduce the recorded results for every valid case."""
import pytest

from tests.conftest import AS_OF, GOLDEN_FILE, case_key, load_json, valid_case_files
from tests.golden_snapshot import snapshot
from app.core.orchestrator import RenewalDeskOrchestrator

GOLDEN = load_json(GOLDEN_FILE)
CASES = valid_case_files()


def test_every_case_has_a_golden_record():
    assert sorted(GOLDEN) == sorted(case_key(p) for p in CASES)


@pytest.mark.parametrize("path", CASES, ids=case_key)
def test_default_policy_matches_golden(path):
    brief = RenewalDeskOrchestrator().run_play(load_json(path), as_of=AS_OF)["brief"]
    assert snapshot(brief) == GOLDEN[case_key(path)]
