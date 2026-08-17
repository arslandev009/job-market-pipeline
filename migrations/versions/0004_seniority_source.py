"""add seniority_source column

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-08

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("postings", sa.Column("seniority_source", sa.String))


def downgrade() -> None:
    op.drop_column("postings", "seniority_source")