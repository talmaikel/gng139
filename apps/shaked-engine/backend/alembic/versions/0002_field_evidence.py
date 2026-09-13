"""Per-field evidence: one row per observed value, with its source, time and certainty

Revision ID: 0002_field_evidence
Revises: 0001_initial_schema
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import fastapi_users_db_sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_field_evidence"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen here rather than imported from app.evidence: a migration must describe
# the schema as it was when written. tests/test_evidence.py checks the two agree.
CERTAINTIES = (
    "official",
    "derived",
    "manually_verified",
    "community",
    "ocr_candidate",
    "ai_candidate",
    "missing",
)


def upgrade() -> None:
    evidence_certainty = postgresql.ENUM(*CERTAINTIES, name="evidence_certainty", create_type=False)
    evidence_certainty.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "field_evidence",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("opportunity_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("field", sa.String(80), nullable=False),
        sa.Column("value", postgresql.JSONB(), nullable=True),
        sa.Column("certainty", evidence_certainty, nullable=False, server_default="missing"),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("feature_url", sa.Text(), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_updated_at", sa.String(64), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("method", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_field_evidence_opportunity_field", "field_evidence", ["opportunity_id", "field"])


def downgrade() -> None:
    op.drop_index("ix_field_evidence_opportunity_field", table_name="field_evidence")
    op.drop_table("field_evidence")
    op.execute("DROP TYPE IF EXISTS evidence_certainty")
