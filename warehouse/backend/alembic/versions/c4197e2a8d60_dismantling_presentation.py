"""Add plan annotations and durable Ukrainian translations, no data backfill."""

from alembic import op
import sqlalchemy as sa

revision = "c4197e2a8d60"
down_revision = "bd18a9f37c20"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dismantling_annotations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("vehicle_id", sa.String(36), nullable=False),
        sa.Column("entry_key", sa.String(100), nullable=False),
        sa.Column("name_uk", sa.String(200), nullable=True),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.Column("dismantled", sa.Boolean(), nullable=False),
        sa.Column(
            "actor_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"]
        ),
        sa.UniqueConstraint(
            "account_id", "vehicle_id", "entry_key", name="uq_dismantling_annotation"
        ),
    )
    op.create_table(
        "part_name_translations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("source_key", sa.String(240), nullable=False),
        sa.Column("original", sa.String(240), nullable=False),
        sa.Column("translated", sa.String(400), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "account_id", "source_key", name="uq_part_name_translation"
        ),
    )


def downgrade():
    raise RuntimeError(
        "Preserve manual names and plan decisions; reviewed roll-forward required"
    )
