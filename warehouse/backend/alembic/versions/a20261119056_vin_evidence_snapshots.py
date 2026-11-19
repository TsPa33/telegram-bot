"""Durable VIN-provider evidence with separate provenance; no historical backfill.

No raw provider JSON, API tokens or cookies are stored.
"""
from alembic import op
import sqlalchemy as sa

revision = "a20261119056"
down_revision = "c42e1109a001"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "vin_evidence_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("vin", sa.String(length=17), nullable=False),
        sa.Column("contract_version", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=28), nullable=False),
        sa.Column("vehicle", sa.JSON(), nullable=False),
        sa.Column("missing", sa.JSON(), nullable=False),
        sa.Column("logo_field_available", sa.Boolean(), nullable=False),
        sa.Column("balance_before", sa.Integer(), nullable=True),
        sa.Column("balance_after", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider","vin","contract_version",
                            name="uq_vin_evidence_provider_vin_version"),
    )
    op.create_index("ix_vin_evidence_snapshots_vin","vin_evidence_snapshots",["vin"])

def downgrade():
    raise RuntimeError("VIN evidence history is forward-only; export and reconcile before removal")
