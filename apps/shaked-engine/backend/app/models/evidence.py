import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.evidence import Certainty


class FieldEvidence(Base):
    """
    One observation of one field of one opportunity.

    Several rows for the same (opportunity_id, field) are expected: a parcel area
    read from GovMap and the same area read from the building file are two
    observations. They are resolved in code (app.evidence.resolve_evidence), so a
    disagreement is kept as a conflict instead of the later row overwriting it.
    """

    __tablename__ = "field_evidence"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    field: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. "parcel_area", "permit_date"
    value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    certainty: Mapped[Certainty] = mapped_column(
        Enum(Certainty, name="evidence_certainty", values_callable=lambda enum_cls: [member.value for member in enum_cls]),
        default=Certainty.MISSING,
        nullable=False,
    )

    source_url: Mapped[str | None] = mapped_column(Text)
    feature_url: Mapped[str | None] = mapped_column(Text)  # the specific record, when the source has one
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_updated_at: Mapped[str | None] = mapped_column(String(64))  # as the source reports it, e.g. SYS_DATE
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    location: Mapped[str | None] = mapped_column(Text)  # where in the source, e.g. "Parcels_ITM.785443.LEGAL_AREA"
    method: Mapped[str | None] = mapped_column(String(120))  # how it was read, e.g. "WFS", "tesseract"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (Index("ix_field_evidence_opportunity_field", "opportunity_id", "field"),)

    def as_observation(self) -> dict[str, Any]:
        """The row in the shape app.evidence reads, so stored and fresh evidence resolve the same way."""
        source = None
        if self.source_url or self.retrieved_at:
            source = {
                "url": self.source_url,
                "feature_url": self.feature_url,
                "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
                "source_updated_at": self.source_updated_at,
                "sha256": self.content_sha256,
            }
        certainty = self.certainty.value if isinstance(self.certainty, Certainty) else self.certainty
        return {
            "value": self.value,
            "certainty": certainty,
            "source": source,
            "location": self.location,
            "method": self.method,
        }
