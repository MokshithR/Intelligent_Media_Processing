"""Initial migration: create images and analysis_results tables.

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

# revision identifiers
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── images table ─────────────────────────────────────────────────────────
    op.create_table(
        "images",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("stored_path", sa.String(1024), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("image_hash", sa.String(64), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "processing", "completed", "failed",
                name="imagestatus",
                create_type=True,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_images_status", "images", ["status"])

    # ── analysis_results table ────────────────────────────────────────────────
    op.create_table(
        "analysis_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "image_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("images.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("check_name", sa.String(64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("details", postgresql.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_analysis_results_image_id", "analysis_results", ["image_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_results_image_id", table_name="analysis_results")
    op.drop_table("analysis_results")
    op.drop_index("ix_images_status", table_name="images")
    op.drop_table("images")
    op.execute("DROP TYPE IF EXISTS imagestatus")
