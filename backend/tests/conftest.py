"""Shared test setup: make `app` importable and expose case loaders."""
import json
import sys
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DATA_DIR = BACKEND_DIR / "data"
SAMPLES_DIR = REPO_DIR / "sample_uploads"
GOLDEN_FILE = Path(__file__).resolve().parent / "golden" / "golden_results.json"

# Fixed assessment date so results do not drift with today's date (see sample_uploads/README.md).
AS_OF = date(2026, 11, 18)


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def valid_case_files() -> list:
    """All case files expected to pass validation: stored cases plus non-422 samples."""
    files = sorted(DATA_DIR.glob("*.json"))
    files += sorted(p for p in SAMPLES_DIR.glob("*.json") if "rejected_422" not in p.name)
    return files


def case_key(path: Path) -> str:
    return f"{path.parent.name}/{path.stem}"


# --------------------------------------------------------------------------- database
import pytest  # noqa: E402

from app.db import database  # noqa: E402
from app.db import models  # noqa: E402,F401  (registers the tables)


@pytest.fixture(autouse=True)
def test_db():
    """Every test gets a fresh in-memory SQLite database; the real SQL Server is never touched."""
    engine = database.configure("sqlite://")
    database.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
