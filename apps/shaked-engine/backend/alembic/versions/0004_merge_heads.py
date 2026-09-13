"""Merge the two 0002 branches: existing_units and field evidence

Both were written against 0001_initial_schema in parallel — main added a single
column to opportunities, the engine branch added per-field evidence and then
parcel identity on top of it. Neither touches what the other changes, so this is
an empty merge point rather than a reconciliation.

Revision ID: 0004_merge_heads
Revises: 0002_add_existing_units, 0003_parcels_and_buildings
Create Date: 2026-09-13
"""

from typing import Sequence, Union

revision: str = "0004_merge_heads"
down_revision: Union[str, Sequence[str], None] = (
    "0002_add_existing_units",
    "0003_parcels_and_buildings",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
