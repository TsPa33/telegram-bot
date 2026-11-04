"""Durable paid Plan.Parts request evidence and supplier brand per assigned stock item.

No catalogue offer payload is persisted and no existing parts are overwritten.
"""
from alembic import op
import sqlalchemy as sa

revision = "e36c9a14b208"
down_revision = "d82f73c4a19e"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("parts", sa.Column("article_brand", sa.String(200), nullable=False, server_default=""))
    op.create_table(
        "plan_parts_article_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("vehicle_id", sa.String(36), nullable=False),
        sa.Column("ktype", sa.Integer(), nullable=False),
        sa.Column("pt_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"], name="fk_pp_receipt_donor_account"),
        sa.UniqueConstraint("account_id", "vehicle_id", "ktype", "pt_id", name="uq_pp_article_receipt_scope"),
        sa.CheckConstraint("ktype > 0 AND pt_id > 0 AND article_count >= 0", name="ck_pp_article_receipt_values"),
        sa.CheckConstraint("status IN ('received','unavailable','uncertain')", name="ck_pp_article_receipt_status")
    )
    op.create_index("ix_pp_article_receipts_vehicle_scope", "plan_parts_article_receipts", ["account_id", "vehicle_id", "ktype"])

def downgrade():
    raise RuntimeError("Historical paid request receipts must not be deleted; use a reviewed roll-forward migration")
