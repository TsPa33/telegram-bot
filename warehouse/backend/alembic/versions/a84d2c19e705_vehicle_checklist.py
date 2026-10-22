"""Separate account-isolated potential-part checklist; no inventory backfill."""
from alembic import op
import sqlalchemy as sa

revision = "a84d2c19e705"
down_revision = "c91e72b6a410"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_vehicles_id_account", "vehicles", ["id", "account_id"])
    op.add_column("vehicles", sa.Column("checklist_ktype", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("checklist_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "vehicle_checklist_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("vehicle_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("ktype", sa.Integer(), nullable=False),
        sa.Column("pt_id", sa.Integer(), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("name_uk", sa.String(200), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"], name="fk_checklist_vehicle_account"),
        sa.UniqueConstraint("vehicle_id", "source", "ktype", "pt_id", name="uq_checklist_vehicle_type"),
        sa.CheckConstraint("ktype > 0 AND pt_id > 0 AND article_count >= 0", name="ck_checklist_provider_values"),
        sa.CheckConstraint("status IN ('unchecked','present','absent','damaged')", name="ck_checklist_status"),
    )
    op.create_index("ix_vehicle_checklist_items_account_id", "vehicle_checklist_items", ["account_id"])
    op.create_index("ix_vehicle_checklist_items_vehicle_id", "vehicle_checklist_items", ["vehicle_id"])


def downgrade():
    op.drop_table("vehicle_checklist_items")
    op.drop_column("vehicles", "checklist_synced_at")
    op.drop_column("vehicles", "checklist_ktype")
    op.drop_constraint("uq_vehicles_id_account", "vehicles", type_="unique")
