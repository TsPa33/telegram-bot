"""Durable pricing reviews and bounded exact-OEM lookup; no price/stock backfill."""
from alembic import op
import sqlalchemy as sa
revision='a6d94c72e310'
down_revision='95c3e7b12a04'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('price_decisions',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('actor_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('request_key',sa.String(36),nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('token',sa.String(64),nullable=False),
        sa.Column('command',sa.JSON(),nullable=False),sa.Column('report',sa.JSON(),nullable=False),sa.Column('status',sa.String(10),nullable=False),sa.Column('apply_key',sa.String(36)),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('account_id','request_key'),sa.UniqueConstraint('account_id','apply_key'),sa.CheckConstraint("status IN ('preview','applied')",name='ck_price_decision_status'))
    op.create_index('ix_price_decisions_account_id','price_decisions',['account_id'])
    op.execute("CREATE INDEX ix_catalogue_price_oem ON catalogue_offers (upper(regexp_replace(normalize(properties->>'oem',NFKC),'\\s+','','g')))")
    op.execute("CREATE INDEX ix_aleto_price_oem ON aleto_offers (account_id,upper(regexp_replace(normalize(oem,NFKC),'\\s+','','g')))")

def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM price_decisions)')):raise RuntimeError('Pricing decisions exist; reviewed roll-forward required')
    op.drop_index('ix_catalogue_price_oem',table_name='catalogue_offers');op.drop_index('ix_aleto_price_oem',table_name='aleto_offers')
    op.drop_table('price_decisions')
