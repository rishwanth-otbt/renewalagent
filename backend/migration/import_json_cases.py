"""
One-time import: copy the case files in backend/tests/fixtures/*.json into the Contracts table.

Run after 001_create_tables.sql, from the backend folder:
    python migration/import_json_cases.py            # import
    python migration/import_json_cases.py --dry-run  # only show what would be imported

A file whose contract JSON is already stored is skipped, so it is safe to run more than once.
Files that fail validation are reported and skipped.
"""
import argparse
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.core.orchestrator import CaseValidationError, validate_case  # noqa: E402
from app.db import repository as repo  # noqa: E402
from app.db.database import session_scope  # noqa: E402
from app.db.models import Contract  # noqa: E402

DATA_DIR = BACKEND_DIR / "tests" / "fixtures"
DISPLAY_NAME_KEY = "_display_name"  # where the old file storage kept the uploaded file name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    files = sorted(DATA_DIR.glob("*.json"))
    added = skipped = failed = 0
    with session_scope() as s:
        stored = set(s.scalars(select(Contract.contract_json)))
        for path in files:
            data = json.loads(path.read_text(encoding="utf-8"))
            name = data.pop(DISPLAY_NAME_KEY, None)
            if json.dumps(data, ensure_ascii=False) in stored:
                print(f"skip     {path.name} (already in the database)")
                skipped += 1
                continue
            try:
                validate_case(data)
            except CaseValidationError as e:
                print(f"INVALID  {path.name}: {'; '.join(e.errors)[:200]}")
                failed += 1
                continue
            display_name = name.strip() if isinstance(name, str) and name.strip() else path.stem.replace("_", " ").title()
            print(f"add      {path.name} as '{display_name}'")
            if not args.dry_run:
                repo.add_contract(
                    s,
                    display_name=display_name,
                    original_filename=name if isinstance(name, str) else path.name,
                    uploaded_by="import from backend/tests/fixtures",
                    data=data,
                )
            added += 1
        if args.dry_run:
            s.rollback()
    print(f"\n{'would add' if args.dry_run else 'added'} {added}, skipped {skipped}, invalid {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
