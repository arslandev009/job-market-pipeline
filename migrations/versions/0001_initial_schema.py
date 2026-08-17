"""initial schema: postings table

Revision ID: 0001
Revises:
Create Date: 2026-07-24

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "postings",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("title", sa.Text),
        sa.Column("company", sa.Text),
        sa.Column("raw_text", sa.Text),
        sa.Column("raw_payload", postgresql.JSONB),
        sa.Column(
            "scraped_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
        ),
        # Phase 5 fields
        sa.Column("salary_min", sa.Integer),
        sa.Column("salary_max", sa.Integer),
        sa.Column("seniority", sa.String),
        sa.Column("remote_or_onsite", sa.String),
        sa.Column("required_skills", postgresql.ARRAY(sa.Text)),
        sa.Column("location", sa.Text),
        sa.Column("extracted_at", sa.TIMESTAMP(timezone=True)),
        # Phase 6 fields
        sa.Column("category_label", sa.String),
        sa.Column("category_label_source", sa.String),
        sa.Column("cluster_id", sa.Integer),
        # Phase 7 fields
        sa.Column("fit_score", sa.Float),
        sa.Column("manual_rating", sa.Integer),
        # Phase 8 fields
        sa.Column("reported_at", sa.TIMESTAMP(timezone=True)),
        sa.UniqueConstraint("url", name="uq_postings_url"),
    )
    op.create_index("idx_postings_source", "postings", ["source"])
    op.create_index("idx_postings_scraped_at", "postings", ["scraped_at"])


def downgrade() -> None:
    op.drop_index("idx_postings_scraped_at", table_name="postings")
    op.drop_index("idx_postings_source", table_name="postings")
    op.drop_table("postings")
