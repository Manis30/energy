"""SQLAlchemy 2.x models for the four approved source-aligned factory tables."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.upload_history import UploadHistory


class DimProduct(Base):
    """Product dimension representing manufacturing product catalog (11 columns)."""

    __tablename__ = "dim_product"

    product_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    product_name: Mapped[str] = mapped_column(String(100), nullable=False)
    product_family: Mapped[str] = mapped_column(String(50), nullable=False)
    ram: Mapped[str] = mapped_column(String(20), nullable=False)
    storage: Mapped[str] = mapped_column(String(20), nullable=False)
    display: Mapped[str] = mapped_column(String(50), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(20), nullable=False)
    standard_cycle_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    standard_unit_cost_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    active_from: Mapped[date] = mapped_column(Date, nullable=False)
    active_to: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        CheckConstraint("standard_cycle_sec > 0", name="chk_dim_product_cycle_sec"),
        CheckConstraint("standard_unit_cost_inr >= 0", name="chk_dim_product_unit_cost"),
        CheckConstraint("active_to >= active_from", name="chk_dim_product_dates"),
    )

    # Relationships
    production_events: Mapped[List["FactHourlyProduction"]] = relationship(
        back_populates="product",
    )


class DimProductionLine(Base):
    """Production line dimension representing plant lines and areas (6 columns)."""

    __tablename__ = "dim_production_line"

    line_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    line_type: Mapped[str] = mapped_column(String(50), nullable=False)
    nominal_capacity_per_hour: Mapped[int] = mapped_column(Integer, nullable=False)
    takt_time_sec: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    area: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint("line_id", "plant_id", name="uq_dim_production_line_line_plant"),
        CheckConstraint("nominal_capacity_per_hour > 0", name="chk_dim_line_capacity"),
        CheckConstraint("takt_time_sec > 0", name="chk_dim_line_takt_time"),
        Index("idx_dim_line_plant_id", "plant_id"),
    )

    # Relationships
    production_events: Mapped[List["FactHourlyProduction"]] = relationship(
        back_populates="production_line",
    )


class FactEnergyMeterHourly(Base):
    """Hourly energy measurements across discrete plant meters (14 columns)."""

    __tablename__ = "fact_energy_meter_hourly"

    meter_reading_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    meter_id: Mapped[str] = mapped_column(String(50), nullable=False)
    area: Mapped[str] = mapped_column(String(50), nullable=False)
    energy_source: Mapped[str] = mapped_column(String(50), nullable=False)
    consumption_kwh: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    demand_kw: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    power_factor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    tariff_inr_per_kwh: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    cost_inr: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    co2e_kg: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    reading_quality: Mapped[str] = mapped_column(String(20), nullable=False)

    # Provenance fields (nullable for backward compatibility with historical records)
    upload_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("upload_history.upload_id", name="fk_fact_energy_upload_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ingested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("timestamp", "plant_id", "meter_id", name="uq_energy_meter_hourly"),
        CheckConstraint("consumption_kwh >= 0", name="chk_energy_consumption_positive"),
        CheckConstraint("demand_kw >= 0", name="chk_energy_demand_positive"),
        CheckConstraint("power_factor >= 0.0 AND power_factor <= 1.0", name="chk_energy_power_factor_range"),
        CheckConstraint("tariff_inr_per_kwh >= 0", name="chk_energy_tariff_positive"),
        CheckConstraint("cost_inr >= 0", name="chk_energy_cost_positive"),
        CheckConstraint("co2e_kg >= 0", name="chk_energy_co2e_positive"),
        Index("idx_energy_timestamp", "timestamp"),
        Index("idx_energy_plant_meter", "plant_id", "meter_id"),
        Index("idx_energy_meter_area", "area"),
        Index("idx_energy_upload_id", "upload_id"),
        Index("idx_energy_upload_date", "upload_id", "date"),
    )

    # Relationships
    upload: Mapped[Optional["UploadHistory"]] = relationship(
        "UploadHistory",
        foreign_keys=[upload_id],
        back_populates="energy_records",
    )


class FactHourlyProduction(Base):
    """Hourly manufacturing performance, outputs, and downtime facts (23 columns)."""

    __tablename__ = "fact_hourly_production"

    event_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    event_ts: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    day: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    hour: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    line_id: Mapped[str] = mapped_column(String(50), nullable=False)
    shift_id: Mapped[str] = mapped_column(String(10), nullable=False)
    product_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("dim_product.product_id", name="fk_production_product_id"),
        nullable=False,
    )
    production_order_id: Mapped[str] = mapped_column(String(50), nullable=False)
    target_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    actual_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    good_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    reject_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    rework_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    downtime_min: Mapped[int] = mapped_column(Integer, nullable=False)
    downtime_reason: Mapped[str] = mapped_column(String(50), nullable=False)
    operator_team: Mapped[str] = mapped_column(String(50), nullable=False)
    source_system: Mapped[str] = mapped_column(String(20), nullable=False)
    data_quality: Mapped[str] = mapped_column(String(20), nullable=False)

    # Provenance fields (nullable for backward compatibility with historical records)
    upload_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("upload_history.upload_id", name="fk_fact_production_upload_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    ingested_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["line_id", "plant_id"],
            ["dim_production_line.line_id", "dim_production_line.plant_id"],
            name="fk_production_line_plant",
        ),
        UniqueConstraint("event_ts", "plant_id", "line_id", name="uq_production_hourly"),
        CheckConstraint("hour >= 0 AND hour <= 23", name="chk_prod_hour_range"),
        CheckConstraint("target_qty >= 0", name="chk_prod_target_qty_positive"),
        CheckConstraint("actual_qty >= 0", name="chk_prod_actual_qty_positive"),
        CheckConstraint("good_qty >= 0", name="chk_prod_good_qty_positive"),
        CheckConstraint("reject_qty >= 0", name="chk_prod_reject_qty_positive"),
        CheckConstraint("rework_qty >= 0", name="chk_prod_rework_qty_positive"),
        CheckConstraint("downtime_min >= 0 AND downtime_min <= 60", name="chk_prod_downtime_range"),
        CheckConstraint("actual_qty = good_qty + reject_qty", name="chk_prod_qty_balance"),
        Index("idx_prod_event_ts", "event_ts"),
        Index("idx_prod_line_id", "line_id"),
        Index("idx_prod_product_id", "product_id"),
        Index("idx_prod_shift_id", "shift_id"),
        Index("idx_prod_plant_id", "plant_id"),
        Index("idx_prod_upload_id", "upload_id"),
        Index("idx_prod_upload_date", "upload_id", "event_date"),
    )

    # Relationships
    product: Mapped["DimProduct"] = relationship(back_populates="production_events")
    production_line: Mapped["DimProductionLine"] = relationship(
        back_populates="production_events",
        foreign_keys=[line_id, plant_id],
    )
    upload: Mapped[Optional["UploadHistory"]] = relationship(
        "UploadHistory",
        foreign_keys=[upload_id],
        back_populates="production_records",
    )


class FactSourceRevision(Base):
    """
    Immutable source telemetry revision for energy and production facts.
    Captures exact numerical precision and source state at time of ingestion or detector execution.
    """

    __tablename__ = "fact_source_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    revision_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    source_table: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_record_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    business_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    upload_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("upload_history.upload_id", name="fk_fact_source_rev_upload_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    revision_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, default=datetime.utcnow, index=True
    )
    source_values_json: Mapped[str] = mapped_column(Text, nullable=False)
    factor_version_id: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    __table_args__ = (
        Index("idx_fsr_source_rec", "source_table", "source_record_id"),
        Index("idx_fsr_business_key", "source_table", "business_key"),
        Index("idx_fsr_plant_id", "plant_id"),
        Index("idx_fsr_upload_id", "upload_id"),
        Index("idx_fsr_is_current", "is_current"),
    )


class DatasetFactorAssumption(Base):
    """
    Versioned tariff and emissions factor assumption record.
    Distinguishes dataset assumptions (approval_status=UNKNOWN) from approved contracts.
    """

    __tablename__ = "dataset_factor_assumptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    factor_id: Mapped[str] = mapped_column(String(60), unique=True, nullable=False, index=True)
    factor_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # ELECTRICITY_TARIFF, GRID_EMISSIONS_FACTOR
    factor_scope: Mapped[str] = mapped_column(String(50), nullable=False, default="DEFAULT")
    numeric_value: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    unit: Mapped[str] = mapped_column(String(30), nullable=False)  # INR/kWh, kg CO2e/kWh
    source_dataset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    approval_status: Mapped[str] = mapped_column(String(40), nullable=False, default="UNKNOWN")  # UNKNOWN, ESTIMATED, UNVERIFIED_DATASET_ASSUMPTION, APPROVED
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    effective_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_hypothetical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_dfa_factor_type", "factor_type"),
    )


class DimMachine(Base):
    """Machine dimension representing physical equipment in plants and lines."""

    __tablename__ = "dim_machine"

    machine_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    machine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    machine_type: Mapped[str] = mapped_column(String(50), nullable=False)
    line_id: Mapped[str] = mapped_column(String(50), nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    criticality: Mapped[str] = mapped_column(String(10), nullable=False)
    commissioned_date: Mapped[date] = mapped_column(Date, nullable=False)
    planned_maintenance_interval_days: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        Index("idx_dim_machine_plant_line", "plant_id", "line_id"),
    )


class DimShiftCalendar(Base):
    """Shift calendar dimension defining planned working shifts and durations."""

    __tablename__ = "dim_shift_calendar"

    calendar_date: Mapped[date] = mapped_column(Date, primary_key=True)
    shift_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    shift_start: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    shift_end: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    planned_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    break_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    is_working_day: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        Index("idx_dim_shift_cal_date", "calendar_date"),
    )


class FactMachineTelemetryHourly(Base):
    """Hourly machine telemetry containing physical sensors, states, and alarms."""

    __tablename__ = "fact_machine_telemetry_hourly"

    telemetry_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    machine_id: Mapped[str] = mapped_column(String(50), ForeignKey("dim_machine.machine_id"), nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    line_id: Mapped[str] = mapped_column(String(50), nullable=False)
    shift_id: Mapped[str] = mapped_column(String(20), nullable=False)
    temperature_c: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    vibration_mm_s: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 3), nullable=True)
    motor_current_a: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    pressure_bar: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    rpm: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 1), nullable=True)
    machine_state: Mapped[str] = mapped_column(String(50), nullable=False)
    alarm_code: Mapped[str] = mapped_column(String(50), nullable=False)
    sensor_health: Mapped[str] = mapped_column(String(50), nullable=False)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (
        Index("idx_fact_mach_telem_plant_line_ts", "plant_id", "line_id", "timestamp"),
        Index("idx_fact_mach_telem_mach_ts", "machine_id", "timestamp"),
        Index("idx_fact_mach_telem_date", "date"),
    )




class FactUtilityTelemetryHourly(Base):
    """Hourly utility telemetry (compressed air, chilled water, HVAC, nitrogen, process water)."""

    __tablename__ = "fact_utility_telemetry_hourly"

    utility_reading_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    utility_type: Mapped[str] = mapped_column(String(50), nullable=False)
    zone: Mapped[str] = mapped_column(String(50), nullable=False)
    flow_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    pressure_bar: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    temperature_c: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    consumption_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    equipment_id: Mapped[str] = mapped_column(String(50), nullable=False)
    operating_status: Mapped[str] = mapped_column(String(50), nullable=False)
    alarm_code: Mapped[str] = mapped_column(String(50), nullable=False)
    upload_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    source_revision_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_fact_util_telem_plant_util_ts", "plant_id", "utility_type", "timestamp"),
        Index("idx_fact_util_telem_equip_ts", "equipment_id", "timestamp"),
        Index("idx_fact_util_telem_type_unit", "utility_type", "consumption_unit"),
    )


class FactDowntimeEvent(Base):
    """Machine and production line downtime events."""

    __tablename__ = "fact_downtime_event"

    downtime_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    machine_id: Mapped[str] = mapped_column(String(50), nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    line_id: Mapped[str] = mapped_column(String(50), nullable=False)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    impact_units: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    maintenance_required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    closure_status: Mapped[str] = mapped_column(String(50), nullable=False)
    upload_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("idx_fact_dt_plant_line_ts", "plant_id", "line_id", "start_ts"),
        Index("idx_fact_dt_mach_ts", "machine_id", "start_ts"),
    )


class FactMaintenanceWorkOrder(Base):
    """Maintenance work orders and repair interventions."""

    __tablename__ = "fact_maintenance_work_order"

    work_order_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    machine_id: Mapped[str] = mapped_column(String(50), nullable=False)
    plant_id: Mapped[str] = mapped_column(String(50), nullable=False)
    created_ts: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    maintenance_type: Mapped[str] = mapped_column(String(50), nullable=False)
    failure_mode: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    planned_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    actual_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=False), nullable=True)
    downtime_avoided_estimate_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    technician_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    upload_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    __table_args__ = (
        Index("idx_fact_mwo_plant_mach_ts", "plant_id", "machine_id", "created_ts"),
        Index("idx_fact_mwo_status", "status"),
    )
