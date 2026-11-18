"""
Regenerate tests/golden/golden_results.json from the current code.

Run only when a result change is intended:  python -m tests.make_golden  (from backend/)
"""
import json

from tests.conftest import AS_OF, GOLDEN_FILE, case_key, load_json, valid_case_files
from tests.golden_snapshot import snapshot
from app.core.orchestrator import RenewalDeskOrchestrator
from app.models.policy_models import RenewalPolicy


def main():
    out = {}
    for path in valid_case_files():
        brief = RenewalDeskOrchestrator().run_play(load_json(path), as_of=AS_OF, policy=RenewalPolicy(), policy_version=0)["brief"]
        out[case_key(path)] = snapshot(brief)
    GOLDEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN_FILE.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(out)} cases to {GOLDEN_FILE}")


if __name__ == "__main__":
    main()
