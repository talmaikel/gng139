"""Add opportunities.existing_units (PRD DOS-02 required minimum input)

Revision ID: 0002_add_existing_units
Revises: 0001_initial_schema
Create Date: 2026-09-12
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_add_existing_units"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("existing_units", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("opportunities", "existing_units")
