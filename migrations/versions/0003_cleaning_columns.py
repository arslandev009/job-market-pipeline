"""add cleaning-stage columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("postings", sa.Column("clean_text", sa.Text))
    op.add_column("postings", sa.Column("is_near_duplicate", sa.Boolean, server_default="false"))
    op.add_column("postings", sa.Column("text_quality_flag", sa.String))
    op.add_column("postings", sa.Column("cleaned_at", sa.TIMESTAMP(timezone=True)))


def downgrade() -> None:
    op.drop_column("postings", "cleaned_at")
    op.drop_column("postings", "text_quality_flag")
    op.drop_column("postings", "is_near_duplicate")
    op.drop_column("postings", "clean_text")