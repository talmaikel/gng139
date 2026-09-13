import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import DateTime, Enum, Float, ForeignKey, Index, Integer, SmallInteger, String, func, text
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
    # Sub-gush suffix (GovMap GUSH_SUFFI). Part of a parcel\'s identity: gush + suffix + parcel.
    block_suffix: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")
    parcel: Mapped[str | None] = mapped_column(String(50))  # Helka
    xplan_code: Mapped[str | None] = mapped_column(String(50), index=True)

    geom: Mapped[str] = mapped_column(Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False)
    area_sqm: Mapped[float | None] = mapped_column(Float)
    # Existing dwelling-unit count "from a sufficient source" (Shaked PRD
    # DOS-02) -- a required minimum input before a dossier counts as ready.
    # NULL means genuinely unknown, not zero.
    existing_units: Mapped[int | None] = mapped_column(Integer)

    verification_level: Mapped[VerificationLevel] = mapped_column(
        Enum(
            VerificationLevel,
            name="verification_level",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=VerificationLevel.RAW,
        nullable=False,
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_opportunities_geom", "geom", postgresql_using="gist"),
        # One row per parcel per city, so re-scanning an area updates rather than duplicates.
        Index(
            "uq_opportunities_parcel",
            "city_code",
            "block",
            "block_suffix",
            "parcel",
            unique=True,
            postgresql_where=text("block IS NOT NULL AND parcel IS NOT NULL"),
        ),
    )
