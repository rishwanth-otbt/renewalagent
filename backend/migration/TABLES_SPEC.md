# Renewal Desk — Database Tables Spec (POC 1)

| | |
|---|---|
| Database | `renewaldesk` |
| Server (local) | `(localdb)\MSSQLLocalDB` — SQL Server 2022 Express LocalDB, Windows login |
| Created by | `001_create_tables.sql` (+ `002_drop_case_number_columns.sql` for databases made with the first version of 001) |
| ORM models | `backend/app/db/models.py` (SQLAlchemy 2.1, driver `mssql-python`) |
| Queries | `backend/app/db/repository.py` |
| Times | SQL Server machine's local time, to the second (`DATETIME2(0)`) |

## Overview

```
Contracts (1) ──< EvaluationResults (many) ──< PdfExports (many)
     └──────────────────────────────────────────< PdfExports (many)
```

| Table | One row per | Written by |
|---|---|---|
| `Contracts` | uploaded contract | `POST /api/upload`, `migration/import_json_cases.py` |
| `EvaluationResults` | click on **Generate brief** | `POST /api/process` |
| `PdfExports` | click on **Export PDF** | `POST /api/exports` |

Contract data lives only in the database. The JSON files in `backend/tests/fixtures/` are test fixtures
for the golden tests; the app never reads or writes them.

---

## 1. `dbo.Contracts`

Each uploaded contract JSON, plus the file name the user sees in the case list.

| Column | Type | Null | Default | Description |
|---|---|---|---|---|
| `ContractId` | `INT IDENTITY(1,1)` | No | auto | Primary key. The case id used by the API and the frontend. |
| `DisplayName` | `NVARCHAR(200)` | No | | Name shown in the case list: the uploaded file name without any folder part (max 120 chars). `"Uploaded contract"` if no name was sent. |
| `OriginalFileName` | `NVARCHAR(260)` | Yes | | File name exactly as the browser sent it. |
| `VendorName` | `NVARCHAR(200)` | Yes | | Copied from `vendor.name` in the JSON, for easy querying. |
| `ContractJson` | `NVARCHAR(MAX)` | No | | Full contract JSON (validated against `RenewalInputData` before saving). |
| `UploadedBy` | `NVARCHAR(100)` | Yes | | Name saved in the browser, if the user has given one; `import from backend/tests/fixtures` for imported rows (older imports say `import from backend/data`). |
| `UploadedAt` | `DATETIME2(0)` | No | `SYSDATETIME()` | When the contract was saved. |

**Constraints**
- `PK_Contracts` — primary key on `ContractId`.
- `CK_Contracts_ContractJson` — `ISJSON(ContractJson) = 1`.
- `DF_Contracts_UploadedAt` — default for `UploadedAt`.

**Notes**
- No separate case number is stored. On upload, the JSON's own `case_id` field (required by the
  schema and printed on the brief) is set to `RENEWAL-<year>-<ContractId, 3 digits>`, e.g. `RENEWAL-2026-010`.
- If two contracts share a `DisplayName`, the case list shows later ones as `name (2)`, `name (3)`.
  The table itself keeps the name unchanged.

---

## 2. `dbo.EvaluationResults`

One row each time a brief is generated (the **Generate brief** button, or the automatic run after an upload).
Viewing a case through `GET /api/case/{id}` does not save anything.

| Column | Type | Null | Default | Description |
|---|---|---|---|---|
| `ResultId` | `INT IDENTITY(1,1)` | No | auto | Primary key. Returned to the browser as `brief.meta.result_id`. |
| `ContractId` | `INT` | No | | The contract that was evaluated → `Contracts.ContractId`. |
| `EvaluatedAt` | `DATETIME2(0)` | No | `SYSDATETIME()` | When the brief was generated. Returned as `brief.meta.evaluated_at`. |
| `AsOfDate` | `DATE` | No | | Assessment date used for the run (the date picker; today if empty). |
| `Decision` | `NVARCHAR(50)` | Yes | | `brief.recommendation.primary`, e.g. `Renew`, `Renegotiate`. |
| `RiskLevel` | `NVARCHAR(20)` | Yes | | `brief.risks.overall_level`, e.g. `High`. |
| `PolicyVersion` | `INT` | Yes | | `brief.meta.policy_version`: the renewal-policy version the run used (0 = built-in defaults). |
| `ResultJson` | `NVARCHAR(MAX)` | No | | The full brief as returned to the browser (before `result_id` / `evaluated_at` are added). |

**Constraints and indexes**
- `PK_EvaluationResults` — primary key on `ResultId`.
- `FK_EvaluationResults_Contracts` — `ContractId` → `Contracts.ContractId`.
- `CK_EvaluationResults_ResultJson` — `ISJSON(ResultJson) = 1`.
- `DF_EvaluationResults_EvaluatedAt` — default for `EvaluatedAt`.
- `IX_EvaluationResults_ContractId` — on `(ContractId, EvaluatedAt)`.

---

## 3. `dbo.PdfExports`

One row each time someone exports a generated brief as PDF. The browser asks for the user's
name (remembered for next time), saves this row, prints "Exported by <name> on <time>" at the
top of the PDF, then opens the print dialog. If the row cannot be saved, the PDF is not opened.

| Column | Type | Null | Default | Description |
|---|---|---|---|---|
| `ExportId` | `INT IDENTITY(1,1)` | No | auto | Primary key. |
| `ContractId` | `INT` | No | | The exported contract → `Contracts.ContractId` (copied from the result). |
| `ResultId` | `INT` | No | | The exported brief → `EvaluationResults.ResultId`. |
| `ExportedBy` | `NVARCHAR(100)` | No | | Name the user typed (trimmed, required). |
| `ExportedAt` | `DATETIME2(0)` | No | `SYSDATETIME()` | When the export was recorded. |

**Constraints and indexes**
- `PK_PdfExports` — primary key on `ExportId`.
- `FK_PdfExports_Contracts` — `ContractId` → `Contracts.ContractId`.
- `FK_PdfExports_EvaluationResults` — `ResultId` → `EvaluationResults.ResultId`.
- `DF_PdfExports_ExportedAt` — default for `ExportedAt`.
- `IX_PdfExports_ContractId` — on `(ContractId, ExportedAt)`.

---

## API ↔ tables

| Endpoint | Reads | Writes | Notes |
|---|---|---|---|
| `GET /api/cases` | `Contracts` | — | Returns `cases` (ids) and `items` (`{id, name}`). |
| `POST /api/upload` | — | `Contracts` | Body `{filename, data, uploaded_by?}`; returns `case_id` = `ContractId`. 422 if the JSON is invalid. |
| `POST /api/process` | `Contracts` | `EvaluationResults` | Body `{case_id, as_of?}`; returns the brief with `meta.result_id`. |
| `GET /api/case/{id}` | `Contracts` | — | Read-only run; nothing is saved. |
| `POST /api/exports` | `EvaluationResults` | `PdfExports` | Body `{result_id, exported_by}`. 404 if the result does not exist, 422 if the name is empty. |

A database error returns HTTP 503 with a message to check that SQL Server is running and `DATABASE_URL` is correct.

## Not stored in the database

- Renewal policy versions: still files in `backend/policies/` (policy settings are switched off in this version).
- Users and logins: there is no login; names are typed by the user.

## Changing the tables

Add a new numbered script (`003_...sql`, ...), update `app/db/models.py` to match, and update this spec.

## Useful queries

```sql
USE renewaldesk;

-- Contracts
SELECT ContractId, DisplayName, VendorName, UploadedBy, UploadedAt FROM Contracts ORDER BY ContractId;

-- Latest results
SELECT TOP 20 r.ResultId, c.DisplayName, r.EvaluatedAt, r.AsOfDate, r.Decision, r.RiskLevel
FROM EvaluationResults r JOIN Contracts c ON c.ContractId = r.ContractId
ORDER BY r.ResultId DESC;

-- Who exported what, and when
SELECT e.ExportId, c.DisplayName, e.ExportedBy, e.ExportedAt, r.Decision
FROM PdfExports e
JOIN Contracts c         ON c.ContractId = e.ContractId
JOIN EvaluationResults r ON r.ResultId   = e.ResultId
ORDER BY e.ExportId DESC;

-- A value inside the stored JSON
SELECT ContractId, JSON_VALUE(ContractJson, '$.msa.current_term_end') AS TermEnd FROM Contracts;
```
