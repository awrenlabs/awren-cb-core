"""Initial schema: create entities, relationships, and events tables.

Revision ID: 0001
Revises: None
Create Date: 2026-06-06
"""
from typing import Any, Optional
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Optional[str] = None
branch_labels: Optional[str] = None
depends_on: Optional[str] = None


def upgrade() -> None:
    op.create_table(
        "entities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(255), nullable=False, index=True),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("identifiers", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "relationships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(255), nullable=False, index=True),
        sa.Column("source_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("target_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("properties", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(255), nullable=False, index=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            index=True,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("source", sa.String(255), nullable=False, server_default="system"),
        sa.Column("subject_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("object_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("events")
    op.drop_table("relationships")
    op.drop_table("entities")
