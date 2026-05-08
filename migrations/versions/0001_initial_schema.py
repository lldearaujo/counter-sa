"""Initial schema: streams, crossing_events, count_snapshots

Revision ID: 0001
Revises:
Create Date: 2026-05-08

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "streams",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("rtsp_url", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("config_json", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "crossing_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("stream_id", sa.Text(), sa.ForeignKey("streams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_name", sa.Text(), nullable=False),
        sa.Column("class_name", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "idx_crossing_events_stream_time",
        "crossing_events",
        ["stream_id", sa.text("occurred_at DESC")],
    )

    op.create_table(
        "count_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("stream_id", sa.Text(), sa.ForeignKey("streams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("zone_name", sa.Text(), nullable=False),
        sa.Column("class_name", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("bucket_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.UniqueConstraint(
            "stream_id", "zone_name", "class_name", "direction", "bucket_time",
            name="uq_count_snapshots",
        ),
    )
    op.create_index(
        "idx_count_snapshots_stream_time",
        "count_snapshots",
        ["stream_id", sa.text("bucket_time DESC")],
    )


def downgrade() -> None:
    op.drop_table("count_snapshots")
    op.drop_table("crossing_events")
    op.drop_table("streams")
