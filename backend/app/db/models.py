"""
ORM models for the three tables in backend/migration/001_create_tables.sql.

The SQL script is the source of truth for the real database; keep these in step with it.
Python attribute names are snake_case; the column names match the SQL (PascalCase).
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Unicode, UnicodeText
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Mapped, mapped_column

try:
    from backend.app.db.database import Base
except ImportError:
    from app.db.database import Base

# DATETIME2(0) on SQL Server, plain DATETIME elsewhere (SQLite in tests).
Timestamp = DateTime().with_variant(mssql.DATETIME2(precision=0), "mssql")


def _now() -> datetime:
    return datetime.now().replace(microsecond=0)


class Contract(Base):
    __tablename__ = "Contracts"

    id: Mapped[int] = mapped_column("ContractId", Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column("DisplayName", Unicode(200), nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column("OriginalFileName", Unicode(260))
    vendor_name: Mapped[Optional[str]] = mapped_column("VendorName", Unicode(200))
    contract_json: Mapped[str] = mapped_column("ContractJson", UnicodeText, nullable=False)
    uploaded_by: Mapped[Optional[str]] = mapped_column("UploadedBy", Unicode(100))
    uploaded_at: Mapped[datetime] = mapped_column("UploadedAt", Timestamp, nullable=False, default=_now)


class EvaluationResult(Base):
    __tablename__ = "EvaluationResults"

    id: Mapped[int] = mapped_column("ResultId", Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column("ContractId", ForeignKey("Contracts.ContractId"), nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column("EvaluatedAt", Timestamp, nullable=False, default=_now)
    as_of_date: Mapped[date] = mapped_column("AsOfDate", Date, nullable=False)
    decision: Mapped[Optional[str]] = mapped_column("Decision", Unicode(50))
    risk_level: Mapped[Optional[str]] = mapped_column("RiskLevel", Unicode(20))
    policy_version: Mapped[Optional[int]] = mapped_column("PolicyVersion", Integer)
    result_json: Mapped[str] = mapped_column("ResultJson", UnicodeText, nullable=False)


class PdfExport(Base):
    __tablename__ = "PdfExports"

    id: Mapped[int] = mapped_column("ExportId", Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column("ContractId", ForeignKey("Contracts.ContractId"), nullable=False)
    result_id: Mapped[int] = mapped_column("ResultId", ForeignKey("EvaluationResults.ResultId"), nullable=False)
    exported_by: Mapped[str] = mapped_column("ExportedBy", Unicode(100), nullable=False)
    exported_at: Mapped[datetime] = mapped_column("ExportedAt", Timestamp, nullable=False, default=_now)
