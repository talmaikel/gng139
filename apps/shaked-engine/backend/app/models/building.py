import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Building(Base):
    """
    A building standing on a parcel (an Opportunity).

    Shaked eligibility is decided per plot, but several of its conditions are per
    building: original permit year, units built under permit, floors, seismic
    strengthening. Those facts are FieldEvidence rows that point at the building;
    facts about the land itself (area, zoning) point at the parcel only.

    `source_key` names where the building was found, e.g. "osm:way:385608705" or
    "municipal-file:5848". It is unique per parcel, so ingesting the same source
    again updates the building instead of adding a second copy of it.
    """

    __tablename__ = "buildings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)
    geom: Mapped[str | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True
    )
    address: Mapped[str | None] = mapped_column(String(500))
    footprint_area_sqm: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("opportunity_id", "source_key", name="uq_buildings_opportunity_source"),
        Index("ix_buildings_geom", "geom", postgresql_using="gist"),
    )
