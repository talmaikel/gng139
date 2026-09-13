"""Add 'estimate' to evidence_certainty

Existing built area is footprint x floors x k, and k is calibrated on a single permit.
Marking that DERIVED would let usable() treat it as able to decide a check, which it is
not: it is computed from official inputs but rests on an assumption, and the difference
matters precisely because the figure is multiplied by four to reach the rights cap.

DERIVED and ESTIMATE are not the same claim, and the enum had no way to say the second.
ESTIMATE stays outside DECIDING, so an estimate can be shown and never decides.

Revision ID: 0005_certainty_estimate
Revises: 0004_merge_heads
Create Date: 2026-09-13
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_certainty_estimate"
down_revision: Union[str, None] = "0004_merge_heads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE evidence_certainty ADD VALUE IF NOT EXISTS 'estimate'")


def downgrade() -> None:
    # Postgres cannot drop a value from an enum type in place; removing it would mean
    # rebuilding the type and rewriting every row that uses it. Deliberately not done.
    pass
