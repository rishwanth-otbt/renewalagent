# Database (SQL Server, `renewaldesk`)

The app stores data in three tables:

| Table | One row per | Main columns |
|---|---|---|
| `Contracts` | uploaded contract | ContractId, DisplayName (shown to the user), OriginalFileName, VendorName, ContractJson, UploadedBy, UploadedAt |
| `EvaluationResults` | click on **Generate brief** | ContractId, EvaluatedAt, AsOfDate, Decision, RiskLevel, PolicyVersion, ResultJson |
| `PdfExports` | click on **Export PDF** | ContractId, ResultId, ExportedBy, ExportedAt |

Times are the SQL Server machine's local time.

## Setup (once)

1. Python packages (from `backend/`):
   ```
   pip install -r requirements.txt
   ```
   On this Windows machine, Application Control blocks SQLAlchemy's compiled speed-up files.
   If `import sqlalchemy` fails with *"An Application Control policy has blocked this file"*,
   install the pure-Python build instead:
   ```
   pip download sqlalchemy==2.1.9 --no-deps --only-binary=:all: --platform any -d wheels
   pip install --force-reinstall --no-deps wheels/sqlalchemy-2.1.9-py3-none-any.whl
   ```
2. Create the database and tables, in SSMS (connect to `(localdb)\MSSQLLocalDB`, open
   `001_create_tables.sql`, Execute) or:
   ```
   sqlcmd -S "(localdb)\MSSQLLocalDB" -E -i migration\001_create_tables.sql
   ```
   A database made with the first version of 001 (which had CaseKey / RenewalId columns) also
   needs `002_drop_case_number_columns.sql`. On a new database it does nothing.
3. Copy the existing case files from `backend/data/` into `Contracts`:
   ```
   python migration/import_json_cases.py
   ```
4. Optional: a different server goes in `backend/.env` (see `backend/.env.example`).

## Code

- `app/db/database.py` — connection (`DATABASE_URL`, default LocalDB + Windows login).
- `app/db/models.py` — ORM models; keep them in step with the SQL script.
- `app/db/repository.py` — the queries the API uses.

Changes to the tables go in a new numbered script (`003_...sql`, ...), and the models are updated to match.

## Useful queries

```sql
USE renewaldesk;
SELECT ContractId, DisplayName, VendorName, UploadedBy, UploadedAt FROM Contracts ORDER BY ContractId;
SELECT TOP 20 r.ResultId, c.DisplayName, r.EvaluatedAt, r.AsOfDate, r.Decision, r.RiskLevel
FROM EvaluationResults r JOIN Contracts c ON c.ContractId = r.ContractId ORDER BY r.ResultId DESC;
SELECT e.ExportId, c.DisplayName, e.ExportedBy, e.ExportedAt, r.Decision
FROM PdfExports e JOIN Contracts c ON c.ContractId = e.ContractId
JOIN EvaluationResults r ON r.ResultId = e.ResultId ORDER BY e.ExportId DESC;
```
