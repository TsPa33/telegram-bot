"""Add product entitlement projection; no legacy credit conversion or live enablement."""

from alembic import op
import sqlalchemy as sa

revision = "a12b34c56d78"
down_revision = "08b72c9d4e16"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "warehouse_entitlement_workspaces",
        sa.Column(
            "workspace_id",
            sa.String(36),
            sa.ForeignKey("accounts.id"),
            primary_key=True,
        ),
        sa.Column("billing_account_id", sa.String(80), nullable=False, unique=True),
        sa.Column(
            "owner_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "mode", sa.String(20), nullable=False, server_default="compatibility"
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("intervals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "trial_used", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.CheckConstraint("mode IN ('compatibility','dry_run','enforce')"),
    )
    op.create_table(
        "warehouse_entitlement_receipts",
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column("digest", sa.String(64), nullable=False),
    )
    op.create_table(
        "warehouse_donor_provenance",
        sa.Column(
            "part_id", sa.String(36), sa.ForeignKey("parts.id"), primary_key=True
        ),
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "vehicle_id", sa.String(36), sa.ForeignKey("vehicles.id"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["part_id", "workspace_id"], ["parts.id", "parts.account_id"]
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id", "workspace_id"], ["vehicles.id", "vehicles.account_id"]
        ),
    )
    op.create_table(
        "warehouse_entitlement_returns",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False
        ),
        sa.Column(
            "sale_id", sa.String(36), sa.ForeignKey("operations.id"), nullable=False
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("request_key", sa.String(80), nullable=False),
        sa.UniqueConstraint("workspace_id", "request_key"),
        sa.CheckConstraint("quantity>0"),
    )
    op.execute("""CREATE FUNCTION immutable_entitlement_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'immutable entitlement evidence'; END $$""")
    for table in (
        "warehouse_donor_provenance",
        "warehouse_entitlement_returns",
        "warehouse_entitlement_receipts",
    ):
        op.execute(
            f"CREATE TRIGGER immutable_entitlement BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION immutable_entitlement_evidence()"
        )


def downgrade():
    tables = (
        "warehouse_entitlement_returns",
        "warehouse_donor_provenance",
        "warehouse_entitlement_receipts",
        "warehouse_entitlement_workspaces",
    )
    connection = op.get_bind()
    if any(
        connection.execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")).scalar()
        for table in tables
    ):
        raise RuntimeError(
            "Preserve projection, provenance and returns. Disable flags instead."
        )
    for table in tables:
        op.drop_table(table)
    op.execute("DROP FUNCTION immutable_entitlement_evidence()")
