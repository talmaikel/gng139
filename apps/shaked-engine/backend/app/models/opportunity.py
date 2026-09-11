import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VerificationLevel(str, enum.Enum):
    RAW = "raw"                # scraped, unverified
    OCR_EXTRACTED = "ocr_extracted"
    AI_ASSISTED = "ai_assisted"
    HUMAN_VERIFIED = "human_verified"


class Opportunity(Base):
    """A candidate parcel/address under the Shaked Alternative urban-renewal track."""

    __tablename__ = "opportunities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    city_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # e.g. "herzliya", "tel_aviv"
    address: Mapped[str] = mapped_column(String(500), nullable=False)
    block: Mapped[str | None] = mapped_column(String(50))   # Gush
    parcel: Mapped[str | None] = mapped_column(String(50))  # Helka
    xplan_code: Mapped[str | None] = mapped_column(String(50), index=True)

    geom: Mapped[str] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False)
    area_sqm: Mapped[float | None] = mapped_column(Float)

    verification_level: Mapped[VerificationLevel] = mapped_column(
        Enum(VerificationLevel, name="verification_level"), default=VerificationLevel.RAW, nullable=False
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_opportunities_geom", "geom", postgresql_using="gist"),
    )
