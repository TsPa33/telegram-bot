"""Optional part color characteristics; no backfill or stock/financial changes."""
from alembic import op
import sqlalchemy as sa
revision='b7e14d90c2f6'
down_revision='a6d94c72e310'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('parts',sa.Column('color_name',sa.String(80),nullable=True))
    op.add_column('parts',sa.Column('paint_code',sa.String(40),nullable=True))

def downgrade():
    # Never erase captured characteristics through an unattended downgrade.
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM parts WHERE color_name IS NOT NULL OR paint_code IS NOT NULL)')):
        raise RuntimeError('Part colors exist; use a reviewed roll-forward')
    op.drop_column('parts','paint_code')
    op.drop_column('parts','color_name')
