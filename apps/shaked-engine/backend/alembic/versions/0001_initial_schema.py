"""Initial schema: tenants, users, opportunities, packages/balances/reservations, task_queue

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-11
"""
from typing import Sequence, Union

import fastapi_users_db_sqlalchemy
import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "tenants",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "users",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(1024), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("full_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.Column("company_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["tenants.id"], ondelete="CASCADE"),
    )

    verification_level = postgresql.ENUM(
        "raw", "ocr_extracted", "ai_assisted", "human_verified", name="verification_level", create_type=False
    )
    verification_level.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "opportunities",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("city_code", sa.String(50), nullable=False, index=True),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("block", sa.String(50), nullable=True),
        sa.Column("parcel", sa.String(50), nullable=True),
        sa.Column("xplan_code", sa.String(50), nullable=True, index=True),
        sa.Column("geom", Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False),
        sa.Column("area_sqm", sa.Float(), nullable=True),
        sa.Column("verification_level", verification_level, nullable=False, server_default="raw"),
        sa.Column("metadata_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_opportunities_geom", "opportunities", ["geom"], postgresql_using="gist")

    op.create_table(
        "packages",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("price_ils", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "balances",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("company_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False, unique=True),
        sa.Column("credits_remaining", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["tenants.id"], ondelete="CASCADE"),
    )

    reservation_status = postgresql.ENUM(
        "active", "released", "converted", name="reservation_status", create_type=False
    )
    reservation_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "reservations",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("opportunity_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("company_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=False),
        sa.Column("status", reservation_status, nullable=False, server_default="active"),
        sa.Column("locked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    # Only one ACTIVE reservation may exist per opportunity, so a locked parcel
    # cannot be served to a second, competing tenant while the lock holds.
    op.create_index(
        "ux_reservations_active_opportunity",
        "reservations",
        ["opportunity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    task_status = postgresql.ENUM(
        "pending", "in_progress", "done", "failed", name="task_status", create_type=False
    )
    task_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "task_queue",
        sa.Column("id", fastapi_users_db_sqlalchemy.generics.GUID(), primary_key=True),
        sa.Column("task_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("status", task_status, nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("company_id", fastapi_users_db_sqlalchemy.generics.GUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["tenants.id"], ondelete="CASCADE"),
    )
    # Powers `SELECT ... FOR UPDATE SKIP LOCKED` claims (see app/core/queue.py).
    op.create_index("ix_task_queue_status_created_at", "task_queue", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("task_queue")
    op.execute("DROP TYPE IF EXISTS task_status")
    op.drop_table("reservations")
    op.execute("DROP TYPE IF EXISTS reservation_status")
    op.drop_table("balances")
    op.drop_table("packages")
    op.drop_table("opportunities")
    op.execute("DROP TYPE IF EXISTS verification_level")
    op.drop_table("users")
    op.drop_table("tenants")
