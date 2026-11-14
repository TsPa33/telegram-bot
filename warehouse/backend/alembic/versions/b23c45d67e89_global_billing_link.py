"""Explicit operational financial identity on existing product projection; no ledger."""
from alembic import op
import sqlalchemy as sa
revision='b23c45d67e89'
down_revision='a12b34c56d78'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('warehouse_entitlement_workspaces',sa.Column('source_environment',sa.String(20),nullable=False,server_default='test'))
    op.add_column('warehouse_entitlement_workspaces',sa.Column('global_binding_id',sa.String(80),nullable=True))
    op.create_check_constraint('ck_entitlement_source_environment','warehouse_entitlement_workspaces',"source_environment IN ('test','sandbox','production')")

def downgrade():
    raise RuntimeError('Preserve canonical Billing identities and snapshots; roll forward or disable routing')
