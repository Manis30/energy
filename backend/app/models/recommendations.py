"""SQLAlchemy models for persistent recommendations and corrective actions."""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.findings import FindingOccurrence, OperationalFinding


class OperationalRecommendation(Base):
    """
    Persistent operational recommendation derived from energy/production findings.
    
    Provides actionable guidance, category classification, and operational prioritization
    without fabricated financial or energy savings claims.
    """

    __tablename__ = "operational_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    
    # Linked source finding and triggering occurrence
    finding_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("operational_findings.finding_id", name="fk_op_rec_finding_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    occurrence_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("finding_occurrences.occurrence_id", name="fk_op_rec_occurrence_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    plant_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="MEDIUM",
        index=True,
    )  # CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
        index=True,
    )  # OPEN, IN_PROGRESS, IMPLEMENTED, DISMISSED

    # Evidence and contextual data reference (JSON string)
    evidence_context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Lifecycle timestamps
    implemented_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    dismissed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    dismissed_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        UniqueConstraint("recommendation_id", name="uq_op_recommendations_rec_id"),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'IMPLEMENTED', 'DISMISSED')",
            name="chk_recommendation_status",
        ),
        CheckConstraint(
            "priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFORMATIONAL')",
            name="chk_recommendation_priority",
        ),
        Index(
            "uq_active_rec_finding_category",
            "finding_id",
            "category",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'IN_PROGRESS')"),
            sqlite_where=text("status IN ('OPEN', 'IN_PROGRESS')"),
        ),
        Index("idx_rec_plant_status", "plant_id", "status"),
        Index("idx_rec_finding_id", "finding_id"),
        Index("idx_rec_occurrence_id", "occurrence_id"),
        Index("idx_rec_priority", "priority"),
        Index("idx_rec_category", "category"),
        Index("idx_rec_created_at", "created_at"),
    )

    finding: Mapped[Optional["OperationalFinding"]] = relationship(
        "OperationalFinding",
        back_populates="recommendations",
        foreign_keys=[finding_id],
    )
    occurrence: Mapped[Optional["FindingOccurrence"]] = relationship(
        "FindingOccurrence",
        foreign_keys=[occurrence_id],
    )
    actions: Mapped[List["CorrectiveAction"]] = relationship(
        "CorrectiveAction",
        back_populates="recommendation",
        cascade="all, delete-orphan",
        order_by="asc(CorrectiveAction.created_at)",
    )
    audit_logs: Mapped[List["RecommendationAuditLog"]] = relationship(
        "RecommendationAuditLog",
        back_populates="recommendation",
        cascade="save-update, merge",
        order_by="desc(RecommendationAuditLog.performed_at)",
    )


class CorrectiveAction(Base):
    """
    Persistent corrective action item tracked under an operational recommendation.
    
    Supports task tracking, assignment, due date management, and verified completion notes.
    """

    __tablename__ = "corrective_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    
    recommendation_id: Mapped[str] = mapped_column(
        String(60),
        ForeignKey("operational_recommendations.recommendation_id", name="fk_action_recommendation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="OPEN",
        index=True,
    )  # OPEN, IN_PROGRESS, COMPLETED, CANCELLED

    owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        UniqueConstraint("action_id", name="uq_corrective_actions_action_id"),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="chk_action_status",
        ),
        Index("idx_action_recommendation_id", "recommendation_id"),
        Index("idx_action_status", "status"),
        Index("idx_action_owner", "owner"),
        Index("idx_action_due_date", "due_date"),
        Index("idx_action_created_at", "created_at"),
    )

    recommendation: Mapped["OperationalRecommendation"] = relationship(
        "OperationalRecommendation",
        back_populates="actions",
        foreign_keys=[recommendation_id],
    )
    audit_logs: Mapped[List["ActionAuditLog"]] = relationship(
        "ActionAuditLog",
        back_populates="corrective_action",
        cascade="save-update, merge",
        order_by="desc(ActionAuditLog.performed_at)",
    )


class RecommendationAuditLog(Base):
    """
    Append-only audit trail tracking operational recommendation lifecycle transitions and modifications.
    """

    __tablename__ = "recommendation_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)

    recommendation_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("operational_recommendations.recommendation_id", name="fk_rec_audit_rec_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_fields_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audit_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("audit_id", name="uq_rec_audit_id"),
        Index("idx_rec_audit_entity_perf", "entity_id", "performed_at"),
        Index("idx_rec_audit_rec_perf", "recommendation_id", "performed_at"),
    )

    recommendation: Mapped[Optional["OperationalRecommendation"]] = relationship(
        "OperationalRecommendation",
        back_populates="audit_logs",
        foreign_keys=[recommendation_id],
    )


class ActionAuditLog(Base):
    """
    Append-only audit trail tracking corrective action lifecycle transitions, ownership changes, and due dates.
    """

    __tablename__ = "action_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    audit_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)

    action_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("corrective_actions.action_id", name="fk_act_audit_act_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recommendation_id: Mapped[Optional[str]] = mapped_column(
        String(60),
        ForeignKey("operational_recommendations.recommendation_id", name="fk_act_audit_rec_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    entity_id: Mapped[str] = mapped_column(String(60), nullable=False, index=True)

    action: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=datetime.utcnow,
        nullable=False,
        index=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changed_fields_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    audit_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("audit_id", name="uq_act_audit_id"),
        Index("idx_act_audit_entity_perf", "entity_id", "performed_at"),
        Index("idx_act_audit_act_perf", "action_id", "performed_at"),
        Index("idx_act_audit_rec_perf", "recommendation_id", "performed_at"),
    )

    corrective_action: Mapped[Optional["CorrectiveAction"]] = relationship(
        "CorrectiveAction",
        back_populates="audit_logs",
        foreign_keys=[action_id],
    )
    recommendation: Mapped[Optional["OperationalRecommendation"]] = relationship(
        "OperationalRecommendation",
        foreign_keys=[recommendation_id],
    )

