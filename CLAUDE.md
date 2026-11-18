# Renewal Desk

Recommends Renew / Renegotiate / Switch for an IT vendor renewal and shows an executive brief.

**Stack:** Python 3.12 + FastAPI · SQL Server via SQLAlchemy (`mssql-python`) · plain HTML/CSS/JS frontend · pytest.

## Where to look

| Need | Read |
| --- | --- |
| What the system does, moves, endpoints, folder layout, tech stack | `SPEC.md` |
| Database tables and columns | `backend/migration/TABLES_SPEC.md` |
| Database setup, connection, migrations | `backend/migration/README.md` |
| Decision thresholds (Renew / Renegotiate / Switch, licenses) | `backend/app/models/policy_models.py` |
| Input schema | `backend/app/models/input_models.py` |
| Run the app, tests, policy | `README.md` |
| Roadmap | `MILESTONES.md` |

## Rules

- Run tests from `backend/`: `pytest`.
- Table changes: new numbered script in `backend/migration/` and update `app/db/models.py` + `TABLES_SPEC.md`.
