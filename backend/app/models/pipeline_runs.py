"""SQLAlchemy model for persistent daily downstream pipeline runs."""

from datetime import date, datetime
from typing import Optional
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DailyPipelineRun(Base):
    """Durable daily operations pipeline run execution record stored in PostgreSQL."""

    __tablename__ = "daily_pipeline_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    reporting_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    input_batch_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING", index=True)
    current_stage: Mapped[str] = mapped_column(String(50), nullable=False, default="data_upload")
    stage_states_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    items_prepared_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_synchronized_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reused_findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)

    __table_args__ = (
        Index("idx_dpr_date_plant", "reporting_date", "plant_id"),
        Index("idx_dpr_status", "status"),
        Index("idx_dpr_is_current", "is_current"),
    )
