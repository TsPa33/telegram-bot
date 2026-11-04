"""Preserve validated, already-retrieved Plan.Parts article offers per donor/type.

Only adds a nullable column; existing paid-receipt evidence is retained.
No historical supplier responses are invented or re-fetched.
"""
from alembic import op
import sqlalchemy as sa

revision = "ac97f052e1b4"
down_revision = "e36c9a14b208"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("plan_parts_article_receipts",
                  sa.Column("article_snapshot", sa.JSON(), nullable=True))


def downgrade():
    raise RuntimeError("Article snapshots may contain paid customer data; use a reviewed roll-forward migration")
