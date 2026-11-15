"""SQLAlchemy models for persistent operational energy findings, occurrence evidence, and lifecycle audit trail."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.upload_history import UploadHistory
    from app.models.recommendations import OperationalRecommendation


class OperationalFinding(Base):
    """
    Persistent operational finding representing a deduplicated, trackable energy or power quality anomaly.
    
    Maintains current lifecycle status, occurrence count, latest evidence, and investigation notes.
    """

    __tablename__ = "operational_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    finding_key: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    
    anomaly_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    meter_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    line_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    
    # Lifecycle state
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="NEW",
        index=True,
    )  # NEW, ACKNOWLEDGED, INVESTIGATING, RESOLVED, REOPENED
    
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
        index=True,
    )  # CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL

    # Detection timeline
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    last_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Current telemetry evidence snapshot
    current_actual_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    current_baseline_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    current_deviation_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Lifecycle workflow fields
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    investigated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    investigation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reopened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    reopen_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("finding_id", name="uq_operational_findings_finding_id"),
        UniqueConstraint("finding_key", name="uq_operational_findings_finding_key"),
        CheckConstraint(
            "status IN ('NEW', 'ACKNOWLEDGED', 'INVESTIGATING', 'RESOLVED', 'REOPENED')",
            name="chk_findings_status",
        ),
        CheckConstraint(
            "severity IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL')",
            name="chk_findings_severity",
        ),
        CheckConstraint("occurrence_count >= 1", name="chk_findings_occurrence_count"),
        Index("idx_findings_plant_status", "plant_id", "status"),
        Index("idx_findings_plant_meter", "plant_id", "meter_id"),
        Index("idx_findings_severity", "severity"),
        Index("idx_findings_last_detected", "last_detected_at"),
    )

    # Relationships - append-safe: no delete-orphan to protect audit and occurrence history
    occurrences: Mapped[List["FindingOccurrence"]] = relationship(
        "FindingOccurrence",
        back_populates="finding",
        cascade="save-update, merge",
        order_by="desc(FindingOccurrence.occurrence_ts)",
    )
    audit_logs: Mapped[List["FindingAuditLog"]] = relationship(
        "FindingAuditLog",
        back_populates="finding",
        cascade="save-update, merge",
        order_by="desc(FindingAuditLog.performed_at)",
    )
    recommendations: Mapped[List["OperationalRecommendation"]] = relationship(
        "OperationalRecommendation",
        back_populates="finding",
        cascade="save-update, merge",
        order_by="desc(OperationalRecommendation.created_at)",
    )


class FindingOccurrence(Base):
    """
    Individual detection occurrence preserving immutable mathematical evidence and telemetry bounds.
    """

    __tablename__ = "finding_occurrences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurrence_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    finding_id: Mapped[str] = mapped_column(
        String(60),
        ForeignKey("operational_findings.finding_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    occurrence_ts: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False, index=True)
    actual_value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    baseline_value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    deviation_score: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_flags_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Lineage fields
    source_table: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_record_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    upload_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("upload_history.upload_id", name="fk_finding_occ_upload_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    detector_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint("finding_id", "occurrence_ts", name="uq_finding_occurrence_finding_ts"),
        Index("idx_occ_finding_ts", "finding_id", "occurrence_ts"),
        Index("idx_occ_source_record", "source_table", "source_record_id"),
        Index("idx_occ_upload_id", "upload_id"),
    )

    finding: Mapped["OperationalFinding"] = relationship(
        "OperationalFinding",
        back_populates="occurrences",
    )
    upload: Mapped[Optional["UploadHistory"]] = relationship(
        "UploadHistory",
        foreign_keys=[upload_id],
    )


class FindingAuditLog(Base):
    """
    Audit log tracking lifecycle transitions, acknowledgment, investigation notes, and reopen events.
    """

    __tablename__ = "finding_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    finding_id: Mapped[str] = mapped_column(
        String(60),
        ForeignKey("operational_findings.finding_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    action: Mapped[str] = mapped_column(String(50), nullable=False)  # CREATED, OCCURRENCE_RECORDED, ACKNOWLEDGED, INVESTIGATION_STARTED, NOTES_UPDATED, RESOLVED, REOPENED
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audit_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_audit_finding_performed", "finding_id", "performed_at"),
    )

    finding: Mapped["OperationalFinding"] = relationship(
        "OperationalFinding",
        back_populates="audit_logs",
    )

