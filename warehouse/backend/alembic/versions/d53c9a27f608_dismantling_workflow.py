"""Local dismantling checklist linked to existing inventory, no backfill or stock seed."""
from alembic import op
import sqlalchemy as sa

revision = "d53c9a27f608"
down_revision = "b72f03d8e196"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dismantling_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("vehicle_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("catalog_key", sa.String(100), nullable=False),
        sa.Column("category_key", sa.String(100), nullable=False),
        sa.Column("category_name", sa.String(100), nullable=False),
        sa.Column("subcategory_key", sa.String(100), nullable=False),
        sa.Column("subcategory_name", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("position", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("condition", sa.String(30), nullable=True),
        sa.Column("part_id", sa.String(36), sa.ForeignKey("parts.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"], name="fk_dismantling_vehicle_account"),
        sa.UniqueConstraint("vehicle_id", "source", "catalog_key", name="uq_dismantling_catalog_key"),
        sa.UniqueConstraint("part_id", name="uq_dismantling_part"),
        sa.CheckConstraint("status IN ('unchecked','dismantled','absent','damaged')", name="ck_dismantling_status"),
        sa.CheckConstraint("quantity > 0 AND quantity <= 1000000", name="ck_dismantling_quantity"),
        sa.CheckConstraint("condition IS NULL OR condition IN ('used','new','damaged','refurbished')", name="ck_dismantling_condition"),
        sa.CheckConstraint("(received_at IS NULL AND part_id IS NULL) OR (received_at IS NOT NULL AND part_id IS NOT NULL)", name="ck_dismantling_receipt_link"),
    )
    op.create_index("ix_dismantling_items_account_id", "dismantling_items", ["account_id"])
    op.create_index("ix_dismantling_items_vehicle_id", "dismantling_items", ["vehicle_id"])


def downgrade():
    # Inventory and its immutable audit survive even if workflow state is removed.
    op.drop_table("dismantling_items")
