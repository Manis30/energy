"""SQLAlchemy 2.x models for the four approved source-aligned factory tables."""

from datetime import date, datetime
from decimal import Decimal
from typing import List

from sqlalchemy import (
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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


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
    )

    # Relationships
    product: Mapped["DimProduct"] = relationship(back_populates="production_events")
    production_line: Mapped["DimProductionLine"] = relationship(
        back_populates="production_events",
        foreign_keys=[line_id, plant_id],
    )
