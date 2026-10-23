"""Explicit sale currency and stock request replay guard. No price conversion."""
from alembic import op
import sqlalchemy as sa
revision='c24a9b71e603'
down_revision='e17b6c04a932'
branch_labels=None
depends_on=None


def upgrade():
    # The preceding model/UI/API denominated all existing prices in UAH.
    op.add_column('parts',sa.Column('currency',sa.String(3),nullable=False,server_default='UAH'))
    op.create_check_constraint('ck_part_currency','parts',"currency IN ('UAH','USD')")
    op.create_table('stock_requests',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('part_id',sa.String(36),sa.ForeignKey('parts.id'),nullable=False),
        sa.Column('request_key',sa.String(36),nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('response',sa.JSON(),nullable=False),
        sa.UniqueConstraint('account_id','request_key',name='uq_stock_request_account_key'))
    op.create_index('ix_stock_requests_account_id','stock_requests',['account_id'])


def downgrade():
    # Refuse to discard currency evidence or replay protection after real use.
    db=op.get_bind()
    if db.execute(sa.text("SELECT EXISTS(SELECT 1 FROM parts WHERE currency <> 'UAH') OR EXISTS(SELECT 1 FROM stock_requests)")).scalar():
        raise RuntimeError('Cannot discard non-UAH prices or stock replay history; rollback application instead')
    op.drop_table('stock_requests')
    op.drop_constraint('ck_part_currency','parts',type_='check')
    op.drop_column('parts','currency')
