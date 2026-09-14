import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.evidence import Certainty


class DwellingUnit(Base):
    """
    One dwelling unit (apartment) in an existing building, with its own area
    and its own provenance.

    **Why a table and not FieldEvidence rows.** FieldEvidence is keyed by
    (opportunity_id, field) and resolved per field; twenty-eight apartments
    would have to become twenty-eight synthetic field names
    ("unit_area_1"...), which `resolve_evidence` cannot compare and no report
    can iterate. Tenant compensation is allocated per household, so the unit
    is a real entity in this domain, not an attribute of the building.

    **Certainty per unit, not per building.** A gramoshka can be legible for
    the ground floor and smudged for the top one. Each row therefore carries
    its own `certainty`, and only `manually_verified` (or another member of
    `app.evidence.DECIDING`) may decide anything downstream -- an
    `ocr_candidate` row is displayed and never allocated against.

    **These are permitted areas, not as-built areas.** A gramoshka records
    what the permit approved. Balcony closures, additions and re-partitions
    made since may never have returned to the file, which is why
    `unit_count_conflict` on the extraction result (permit count vs. the
    municipal `num_aprt`) is kept rather than reconciled away.
    """

    __tablename__ = "dwelling_units"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    # Null when the source names apartments without attributing them to one of
    # several buildings on the parcel -- common on older single-sheet plans.
    building_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True
    )

    # Stable identity of the unit within one extraction run, so re-running the
    # pipeline updates rows instead of duplicating them. When the source gives
    # no apartment number, the ordinal position on the sheet is used and
    # `unit_label` stays null -- an honest "the seventh row in the schedule".
    source_key: Mapped[str] = mapped_column(String(120), nullable=False)

    unit_label: Mapped[str | None] = mapped_column(String(40))   # "12", "3א"
    floor: Mapped[str | None] = mapped_column(String(20))        # kept as text: "קרקע", "-1"
    area_sqm: Mapped[float | None] = mapped_column(Float)
    balcony_area_sqm: Mapped[float | None] = mapped_column(Float)
    rooms: Mapped[str | None] = mapped_column(String(20))

    certainty: Mapped[Certainty] = mapped_column(
        Enum(
            Certainty,
            name="evidence_certainty",
            create_type=False,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=Certainty.MISSING,
        nullable=False,
    )
    # True until a person confirms this row against the scan. Mirrors
    # extractor.ExtractionResult.requires_human_review and is never cleared by
    # the pipeline itself.
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    source_url: Mapped[str | None] = mapped_column(Text)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(Text)        # where in the source, e.g. "page 2, schedule row 7"
    method: Mapped[str | None] = mapped_column(String(120))   # "tesseract_regex", "openai_gpt4o_mini", "manual"
    raw_text: Mapped[str | None] = mapped_column(Text)        # the line as read, so a reviewer can check the reading

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("opportunity_id", "source_key", name="uq_dwelling_units_opportunity_source"),
        Index("ix_dwelling_units_opportunity", "opportunity_id"),
        Index("ix_dwelling_units_building", "building_id"),
    )
