"""Persist VIN intake evidence; nullable additive column, no backfill or stock changes."""
from alembic import op
import sqlalchemy as sa
revision='08b72c9d4e16'
down_revision='f7a10b8c43d2'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('vehicles',sa.Column('vin_details',sa.JSON(),nullable=True))

def downgrade():
    raise RuntimeError('Forward-only VIN evidence migration; do not discard saved snapshots')
