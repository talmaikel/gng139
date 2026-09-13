"""Delivery ledger — SEL-02 / ACC-04

‏`reservations` הייתה נעילה זמנית, ולא רישום של מה שכבר נמסר. בלי הרישום
הזה ה-PRD דורש משהו שאין לו איפה לחיות: *״אותו מגרש אינו נספר שוב בעקבות
פוליגון חופף, שינוי כתובת, שינוי משתמש בחברה או חבילה חדשה״*.

האילוץ הייחודי הוא על (opportunity, company) ולא על המשתמש, כי ה-PRD קובע
ש*״תוצאה שנמסרה למשתמש בחברה נחשבת תוצאה שנמסרה לחברה״*.

Revision ID: 0006_deliveries
Revises: 0005_certainty_estimate
Create Date: 2026-09-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_deliveries"
down_revision: Union[str, None] = "0005_certainty_estimate"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delivered_to_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("credits_charged", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rules_version", sa.String(40), nullable=False, server_default=""),
        sa.Column("data_version", sa.String(40), nullable=False, server_default=""),
        sa.Column("why_selected", postgresql.JSONB(), nullable=True),
        sa.UniqueConstraint("opportunity_id", "company_id",
                            name="ux_deliveries_company_opportunity"),
    )
    op.create_index("ix_deliveries_company", "deliveries", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_deliveries_company", table_name="deliveries")
    op.drop_table("deliveries")
