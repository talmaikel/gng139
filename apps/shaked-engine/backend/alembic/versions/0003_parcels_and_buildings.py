"""Parcel identity and buildings: one opportunity per parcel, buildings beneath it, evidence per building

Revision ID: 0003_parcels_and_buildings
Revises: 0002_field_evidence
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import fastapi_users_db_sqlalchemy
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0003_parcels_and_buildings"
down_revision: Union[str, None] = "0002_field_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A parcel is identified by gush + sub-gush suffix + parcel (GovMap GUSH_NUM,
    # GUSH_SUFFI, PARCEL). Without the suffix, two different parcels share a key.
    op.add_column("opportunities", sa.Column("block_suffix", sa.SmallInteger(), nullable=False, server_default="0"))

    # One row per parcel per city, so re-scanning an area updates a parcel instead
    # of adding it again. If duplicates already exist this fails loudly: resolve
    # them first rather than have a migration choose which rows to drop.
    op.create_index(
        "uq_opportunities_parcel",
        "opportunities",
        ["city_code", "block", "block_suffix", "parcel"],
        unique=True,
        postgresql_where=sa.text("block IS NOT NULL AND parcel IS NOT NULL"),
    )

    op.create_table(
        "buildings",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("opportunity_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("source_key", sa.String(120), nullable=False),
        sa.Column("geom", Geometry(geometry_type="MULTIPOLYGON", srid=4326, spatial_index=False), nullable=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("footprint_area_sqm", sa.Float(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("opportunity_id", "source_key", name="uq_buildings_opportunity_source"),
    )
    op.create_index("ix_buildings_geom", "buildings", ["geom"], postgresql_using="gist")

    # Evidence without a building is about the parcel (area, zoning); with one,
    # it is about that building (permit year, units, floors).
    op.add_column("field_evidence", sa.Column("building_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=True))
    op.create_foreign_key(
        "fk_field_evidence_building", "field_evidence", "buildings", ["building_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_field_evidence_building_field", "field_evidence", ["building_id", "field"])


def downgrade() -> None:
    op.drop_index("ix_field_evidence_building_field", table_name="field_evidence")
    op.drop_constraint("fk_field_evidence_building", "field_evidence", type_="foreignkey")
    op.drop_column("field_evidence", "building_id")
    op.drop_index("ix_buildings_geom", table_name="buildings")
    op.drop_table("buildings")
    op.drop_index("uq_opportunities_parcel", table_name="opportunities")
    op.drop_column("opportunities", "block_suffix")
