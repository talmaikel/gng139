"""packages.price_ils: integer -> numeric(10, 2)

Revision ID: 0010_package_price_decimal
Revises: 0009_credit_grants
Create Date: 2026-09-15

The pilot prices are 19.90 / 49.90 ILS. An integer column would have stored
19 or 20 without complaint, and the screen would show a price the customer
was never quoted.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010_package_price_decimal"
down_revision: Union[str, None] = "0009_credit_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("packages", "price_ils", type_=sa.Numeric(10, 2),
                    existing_type=sa.Integer(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("packages", "price_ils", type_=sa.Integer(),
                    existing_type=sa.Numeric(10, 2), existing_nullable=False,
                    postgresql_using="round(price_ils)::integer")
