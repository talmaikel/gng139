import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PropertyTransaction(Base):
    """A factual sale transaction as returned by a named external source."""

    __tablename__ = "property_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_deal_id: Mapped[str] = mapped_column(String(100), nullable=False)
    city_code: Mapped[str | None] = mapped_column(String(50), index=True)
    settlement_name: Mapped[str | None] = mapped_column(String(255))
    street_name: Mapped[str | None] = mapped_column(String(255))
    house_number: Mapped[str | None] = mapped_column(String(50))
    neighborhood: Mapped[str | None] = mapped_column(String(255))
    block: Mapped[str | None] = mapped_column(String(50))
    parcel: Mapped[str | None] = mapped_column(String(50))
    subparcel: Mapped[str | None] = mapped_column(String(50))
    deal_date: Mapped[date] = mapped_column(Date, nullable=False)
    deal_amount_ils: Mapped[float] = mapped_column(Float, nullable=False)
    area_sqm: Mapped[float] = mapped_column(Float, nullable=False)
    rooms: Mapped[float] = mapped_column(Float, nullable=False)
    floor: Mapped[str | None] = mapped_column(String(50))
    property_type: Mapped[str | None] = mapped_column(String(255))
    deal_nature: Mapped[str | None] = mapped_column(String(255))
    price_per_sqm_ils: Mapped[float] = mapped_column(Float, nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "source", "source_deal_id", name="uq_property_transactions_source_deal"
        ),
        Index("ix_property_transactions_lookup", "city_code", "deal_date", "rooms"),
    )


class MarketValuationRun(Base):
    """Immutable, dated calculation snapshot; later runs never overwrite it."""

    __tablename__ = "market_valuation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    lookback_months: Mapped[int] = mapped_column(Integer, nullable=False)
    radius_m: Mapped[int] = mapped_column(Integer, nullable=False)
    comparable_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    parameters_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index(
            "ix_market_valuation_runs_opportunity_created",
            "opportunity_id",
            "created_at",
        ),
    )
