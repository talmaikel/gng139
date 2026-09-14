"""Add factual property transactions and dated market valuation runs.

Revision ID: 0007_add_market_data
Revises: 0006_deliveries
Create Date: 2026-09-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007_add_market_data"
down_revision: str | None = "0006_deliveries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "property_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_deal_id", sa.String(100), nullable=False),
        sa.Column("city_code", sa.String(50), nullable=True),
        sa.Column("settlement_name", sa.String(255), nullable=True),
        sa.Column("street_name", sa.String(255), nullable=True),
        sa.Column("house_number", sa.String(50), nullable=True),
        sa.Column("neighborhood", sa.String(255), nullable=True),
        sa.Column("block", sa.String(50), nullable=True),
        sa.Column("parcel", sa.String(50), nullable=True),
        sa.Column("subparcel", sa.String(50), nullable=True),
        sa.Column("deal_date", sa.Date(), nullable=False),
        sa.Column("deal_amount_ils", sa.Float(), nullable=False),
        sa.Column("area_sqm", sa.Float(), nullable=False),
        sa.Column("rooms", sa.Float(), nullable=False),
        sa.Column("floor", sa.String(50), nullable=True),
        sa.Column("property_type", sa.String(255), nullable=True),
        sa.Column("deal_nature", sa.String(255), nullable=True),
        sa.Column("price_per_sqm_ils", sa.Float(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("raw_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "source", "source_deal_id", name="uq_property_transactions_source_deal"
        ),
    )
    op.create_index(
        "ix_property_transactions_city_code", "property_transactions", ["city_code"]
    )
    op.create_index(
        "ix_property_transactions_lookup",
        "property_transactions",
        ["city_code", "deal_date", "rooms"],
    )

    op.create_table(
        "market_valuation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("opportunity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("lookback_months", sa.Integer(), nullable=False),
        sa.Column("radius_m", sa.Integer(), nullable=False),
        sa.Column("comparable_count", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=False),
        sa.Column("parameters_json", postgresql.JSONB(), nullable=False),
        sa.Column("result_json", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_market_valuation_runs_opportunity_created",
        "market_valuation_runs",
        ["opportunity_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_valuation_runs_opportunity_created",
        table_name="market_valuation_runs",
    )
    op.drop_table("market_valuation_runs")
    op.drop_index("ix_property_transactions_lookup", table_name="property_transactions")
    op.drop_index(
        "ix_property_transactions_city_code", table_name="property_transactions"
    )
    op.drop_table("property_transactions")
