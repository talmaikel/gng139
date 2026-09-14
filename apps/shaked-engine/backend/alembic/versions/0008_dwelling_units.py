"""dwelling_units: per-apartment area with its own provenance

Revision ID: 0008_dwelling_units
Revises: 0007_add_market_data
Create Date: 2026-09-14

The `evidence_certainty` enum already exists (0002/0005); this table reuses it
with `create_type=False` so the migration does not try to create it a second
time -- the same double-creation bug that had to be fixed in 0001.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_dwelling_units"
down_revision: Union[str, None] = "0007_add_market_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CERTAINTY = postgresql.ENUM(
    "official",
    "derived",
    "manually_verified",
    "community",
    "ocr_candidate",
    "ai_candidate",
    "estimate",
    "missing",
    name="evidence_certainty",
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        "dwelling_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "building_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("buildings.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("unit_label", sa.String(40), nullable=True),
        sa.Column("floor", sa.String(20), nullable=True),
        sa.Column("area_sqm", sa.Float(), nullable=True),
        sa.Column("balcony_area_sqm", sa.Float(), nullable=True),
        sa.Column("rooms", sa.String(20), nullable=True),
        sa.Column("certainty", CERTAINTY, nullable=False, server_default="missing"),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("method", sa.String(120), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("opportunity_id", "source_key", name="uq_dwelling_units_opportunity_source"),
    )
    op.create_index("ix_dwelling_units_opportunity", "dwelling_units", ["opportunity_id"])
    op.create_index("ix_dwelling_units_building", "dwelling_units", ["building_id"])


def downgrade() -> None:
    op.drop_index("ix_dwelling_units_building", table_name="dwelling_units")
    op.drop_index("ix_dwelling_units_opportunity", table_name="dwelling_units")
    op.drop_table("dwelling_units")
