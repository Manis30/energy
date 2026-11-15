"""SQLAlchemy model for tracking daily report uploads and ingestion audit history."""

from datetime import date, datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import Date, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.source_data import FactEnergyMeterHourly, FactHourlyProduction


class UploadHistory(Base):
    """Audit trail for daily energy and production file uploads and database ingestions."""

    __tablename__ = "upload_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), default=datetime.utcnow, nullable=False
    )
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ENERGY, PRODUCTION, ENERGY_AND_PRODUCTION
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_format: Mapped[str] = mapped_column(String(20), nullable=False)  # CSV, XLSX, XLS
    sheet_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    reporting_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    total_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)  # COMPLETED, FAILED, PARTIAL, OVERWRITTEN
    mode: Mapped[str] = mapped_column(String(30), nullable=False)  # INCREMENTAL, OVERWRITE_CORRECTION
    audit_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("upload_id", name="uq_upload_history_upload_id"),
        Index("idx_upload_history_report_type", "report_type"),
        Index("idx_upload_history_uploaded_at", "uploaded_at"),
        Index("idx_upload_history_reporting_date", "reporting_date"),
    )

    # Provenance relationships
    energy_records: Mapped[List["FactEnergyMeterHourly"]] = relationship(
        "FactEnergyMeterHourly",
        back_populates="upload",
        foreign_keys="FactEnergyMeterHourly.upload_id",
    )
    production_records: Mapped[List["FactHourlyProduction"]] = relationship(
        "FactHourlyProduction",
        back_populates="upload",
        foreign_keys="FactHourlyProduction.upload_id",
    )


