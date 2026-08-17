"""add runs table for basic pipeline observability

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-24

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("status", sa.String, server_default="running"),
        sa.Column("rows_processed", sa.Integer),
        sa.Column("error_message", sa.Text),
    )
    op.create_index("idx_runs_stage", "runs", ["stage"])


def downgrade() -> None:
    op.drop_index("idx_runs_stage", table_name="runs")
    op.drop_table("runs")
