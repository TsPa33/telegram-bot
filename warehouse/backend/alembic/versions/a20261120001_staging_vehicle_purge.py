"""Allow the scoped staging purge while retaining immutable history by default."""

from alembic import op

revision = "a20261120001"
down_revision = "a20261119056"
branch_labels = None
depends_on = None

TRIGGERS = (
    ("immutable_warehouse_audit", "UPDATE OR DELETE", "operations"),
    ("assembly_history_no_delete", "DELETE", "assembly_memberships"),
)


def bind(function):
    for name, events, table in TRIGGERS:
        op.execute(f"DROP TRIGGER {name} ON {table}")
        op.execute(f"CREATE TRIGGER {name} BEFORE {events} ON {table} "
                   f"FOR EACH ROW EXECUTE FUNCTION {function}()")


def upgrade():
    op.execute("""
        CREATE FUNCTION warehouse_guard_staging_vehicle_purge() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
            scope jsonb := nullif(current_setting('warehouse.staging_vehicle_purge', true), '')::jsonb;
            donor varchar := scope->>'vehicle_id';
            workspace varchar := scope->>'account_id';
        BEGIN
            IF TG_OP = 'DELETE' AND OLD.account_id = workspace AND EXISTS (
                SELECT 1 FROM vehicles v WHERE v.id = donor AND v.account_id = workspace
            ) THEN
                IF TG_TABLE_NAME = 'assembly_memberships' AND OLD.vehicle_id = donor THEN
                    RETURN OLD;
                ELSIF TG_TABLE_NAME = 'operations' THEN
                    IF (OLD.vehicle_id = donor OR OLD.vehicle_id IS NULL AND OLD.part_id IS NOT NULL)
                        AND (OLD.part_id IS NULL OR EXISTS (
                            SELECT 1 FROM parts p WHERE p.id = OLD.part_id
                                AND p.vehicle_id = donor AND p.account_id = workspace
                        ))
                        AND OLD.type NOT IN ('sale', 'return', 'refund', 'assembly_included_sale') THEN
                        RETURN OLD;
                    END IF;
                END IF;
            END IF;
            RAISE EXCEPTION 'Warehouse audit history is immutable';
        END;
        $$
    """)
    bind('warehouse_guard_staging_vehicle_purge')


def downgrade():
    bind('warehouse_reject_audit_change')
    op.execute('DROP FUNCTION warehouse_guard_staging_vehicle_purge()')
