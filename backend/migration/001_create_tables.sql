/*
  Renewal Desk - POC 1 database
  Creates the database `renewaldesk` and its three tables. Safe to run more than once:
  anything that already exists is left as it is.

  Run in SSMS (connect to (localdb)\MSSQLLocalDB, open this file, Execute), or:
    sqlcmd -S "(localdb)\MSSQLLocalDB" -E -i backend\migration\001_create_tables.sql

  Times are the SQL Server machine's local time (SYSDATETIME()).
*/

IF DB_ID(N'renewaldesk') IS NULL
    CREATE DATABASE renewaldesk;
GO

USE renewaldesk;
GO

-- 1. Contracts: one row per uploaded contract (replaces the JSON files in backend/data).
IF OBJECT_ID(N'dbo.Contracts', N'U') IS NULL
CREATE TABLE dbo.Contracts (
    ContractId        INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_Contracts PRIMARY KEY,  -- id used by the API
    DisplayName       NVARCHAR(200) NOT NULL,                                          -- name shown in the case list (uploaded file name)
    OriginalFileName  NVARCHAR(260) NULL,                                              -- file name exactly as uploaded
    VendorName        NVARCHAR(200) NULL,
    ContractJson      NVARCHAR(MAX) NOT NULL CONSTRAINT CK_Contracts_ContractJson CHECK (ISJSON(ContractJson) = 1),
    UploadedBy        NVARCHAR(100) NULL,
    UploadedAt        DATETIME2(0)  NOT NULL CONSTRAINT DF_Contracts_UploadedAt DEFAULT SYSDATETIME()
);
GO

-- 2. EvaluationResults: one row each time a brief is generated.
IF OBJECT_ID(N'dbo.EvaluationResults', N'U') IS NULL
CREATE TABLE dbo.EvaluationResults (
    ResultId       INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_EvaluationResults PRIMARY KEY,
    ContractId     INT           NOT NULL CONSTRAINT FK_EvaluationResults_Contracts REFERENCES dbo.Contracts (ContractId),
    EvaluatedAt    DATETIME2(0)  NOT NULL CONSTRAINT DF_EvaluationResults_EvaluatedAt DEFAULT SYSDATETIME(),
    AsOfDate       DATE          NOT NULL,                                             -- assessment date used for the run
    Decision       NVARCHAR(50)  NULL,                                                 -- e.g. RENEGOTIATE
    RiskLevel      NVARCHAR(20)  NULL,                                                 -- e.g. High
    PolicyVersion  INT           NULL,                                                 -- empty while policy settings are off
    ResultJson     NVARCHAR(MAX) NOT NULL CONSTRAINT CK_EvaluationResults_ResultJson CHECK (ISJSON(ResultJson) = 1)
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_EvaluationResults_ContractId')
    CREATE INDEX IX_EvaluationResults_ContractId ON dbo.EvaluationResults (ContractId, EvaluatedAt);
GO

-- 3. PdfExports: one row each time someone exports a brief as PDF.
IF OBJECT_ID(N'dbo.PdfExports', N'U') IS NULL
CREATE TABLE dbo.PdfExports (
    ExportId    INT IDENTITY(1,1) NOT NULL CONSTRAINT PK_PdfExports PRIMARY KEY,
    ContractId  INT           NOT NULL CONSTRAINT FK_PdfExports_Contracts REFERENCES dbo.Contracts (ContractId),
    ResultId    INT           NOT NULL CONSTRAINT FK_PdfExports_EvaluationResults REFERENCES dbo.EvaluationResults (ResultId),
    ExportedBy  NVARCHAR(100) NOT NULL,
    ExportedAt  DATETIME2(0)  NOT NULL CONSTRAINT DF_PdfExports_ExportedAt DEFAULT SYSDATETIME()
);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_PdfExports_ContractId')
    CREATE INDEX IX_PdfExports_ContractId ON dbo.PdfExports (ContractId, ExportedAt);
GO
