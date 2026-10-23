"""Stable account-local vehicle numbers; preserve all internal identifiers."""
from alembic import op
import sqlalchemy as sa
revision = 'e17b6c04a932'
down_revision = 'f06a41c9d2b7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('vehicles', sa.Column('number', sa.Integer(), nullable=True))
    op.execute("""WITH numbered AS (
        SELECT id, row_number() OVER (PARTITION BY account_id ORDER BY created_at, id) AS n
        FROM vehicles)
        UPDATE vehicles SET number = numbered.n FROM numbered WHERE vehicles.id = numbered.id""")
    op.alter_column('vehicles', 'number', nullable=False)
    op.create_unique_constraint('uq_vehicle_account_number', 'vehicles', ['account_id', 'number'])
    op.create_check_constraint('ck_vehicle_number_positive', 'vehicles', 'number > 0')
    # Permit the previous backend release to create vehicles during a rolling
    # update or application rollback; it does not know about this column yet.
    op.execute("""CREATE FUNCTION warehouse_vehicle_number() RETURNS trigger AS $$
    BEGIN
        IF NEW.number IS NULL THEN
            PERFORM id FROM accounts WHERE id = NEW.account_id FOR UPDATE;
            SELECT COALESCE(MAX(number), 0) + 1 INTO NEW.number
                FROM vehicles WHERE account_id = NEW.account_id;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql""")
    op.execute("""CREATE TRIGGER warehouse_vehicle_number_insert
        BEFORE INSERT ON vehicles FOR EACH ROW EXECUTE FUNCTION warehouse_vehicle_number()""")


def downgrade():
    op.execute('DROP TRIGGER warehouse_vehicle_number_insert ON vehicles')
    op.execute('DROP FUNCTION warehouse_vehicle_number()')
    op.drop_constraint('ck_vehicle_number_positive', 'vehicles', type_='check')
    op.drop_constraint('uq_vehicle_account_number', 'vehicles', type_='unique')
    op.drop_column('vehicles', 'number')
