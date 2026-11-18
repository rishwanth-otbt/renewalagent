/*
  Remove the case-number columns from Contracts. ContractId is the only id now; the user
  sees DisplayName (the uploaded file name).

  Only needed for a database created with the first version of 001_create_tables.sql
  (which had CaseKey and RenewalId). Safe to run more than once; does nothing if they are gone.

    sqlcmd -S "(localdb)\MSSQLLocalDB" -E -i migration\002_drop_case_number_columns.sql
*/

USE renewaldesk;
GO

IF EXISTS (SELECT 1 FROM sys.key_constraints WHERE name = N'UQ_Contracts_CaseKey')
    ALTER TABLE dbo.Contracts DROP CONSTRAINT UQ_Contracts_CaseKey;
GO

IF COL_LENGTH(N'dbo.Contracts', N'CaseKey') IS NOT NULL
    ALTER TABLE dbo.Contracts DROP COLUMN CaseKey;
GO

IF COL_LENGTH(N'dbo.Contracts', N'RenewalId') IS NOT NULL
    ALTER TABLE dbo.Contracts DROP COLUMN RenewalId;
GO
