"""credit_grants: every credit an admin adds, with the payment reference

Revision ID: 0009_credit_grants
Revises: 0008_dwelling_units
Create Date: 2026-09-15

The pilot has no payment processing. The customer pays through a link, gets an
invoice, and an admin adds credits. The self-service purchase route is removed
in the same change; this table is what ties a balance back to an invoice.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_credit_grants"
down_revision: Union[str, None] = "0008_dwelling_units"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "credit_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("package_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("packages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.String(500), nullable=False),
        sa.Column("granted_by_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_credit_grants_company_id", "credit_grants", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_credit_grants_company_id", table_name="credit_grants")
    op.drop_table("credit_grants")
