"""Enforce immutable audit history at the database layer."""

from alembic import op

revision = "f482ab1376c0"
down_revision = "eb8fddfe982f"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION warehouse_reject_audit_change() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Warehouse audit history is immutable'; END; $$""")
    op.execute(
        "CREATE TRIGGER immutable_warehouse_audit BEFORE UPDATE OR DELETE ON operations FOR EACH ROW EXECUTE FUNCTION warehouse_reject_audit_change()"
    )


def downgrade():
    op.execute("DROP TRIGGER immutable_warehouse_audit ON operations")
    op.execute("DROP FUNCTION warehouse_reject_audit_change()")
