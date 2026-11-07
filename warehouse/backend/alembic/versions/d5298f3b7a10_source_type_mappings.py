"""Stable source type decisions only. No backfill or stock-table modification."""

from alembic import op
import sqlalchemy as sa

revision = "d5298f3b7a10"
down_revision = "c4197e2a8d60"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "source_type_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("pt_id", sa.Integer(), nullable=False),
        sa.Column("type_key", sa.String(100), nullable=False),
        sa.Column("source_name", sa.String(240), nullable=False),
        sa.Column("decision", sa.JSON(), nullable=False),
        sa.Column("history", sa.JSON(), nullable=False),
        sa.Column(
            "category_id", sa.String(36), sa.ForeignKey("categories.id"), nullable=True
        ),
        sa.Column(
            "subcategory_id",
            sa.String(36),
            sa.ForeignKey("categories.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("account_id", "source", "pt_id"),
    )


def downgrade():
    raise RuntimeError("Mapping history must be retained; use a reviewed roll-forward")
