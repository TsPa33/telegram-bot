"""Persistent donor plan and account-local catalogue; no inventory mutation."""
from alembic import op
import sqlalchemy as sa
revision='f06a41c9d2b7'
down_revision='d53c9a27f608'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('dismantling_items',sa.Column('included',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_table('dismantling_catalog_sources',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('source',sa.String(100),nullable=False),
        sa.Column('provenance',sa.Text(),nullable=False),
        sa.Column('license_reference',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('account_id','source',name='uq_dcatalog_source'),
        sa.UniqueConstraint('id','account_id',name='uq_dcatalog_source_account'))
    op.create_index('ix_dismantling_catalog_sources_account_id','dismantling_catalog_sources',['account_id'])
    op.create_table('dismantling_catalog_types',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('source_id',sa.String(36),nullable=False),
        *[sa.Column(n,sa.String(200 if n=='name' else 100),nullable=False) for n in
          ['catalog_key','category_key','category_name','subcategory_key','subcategory_name','name','position']],
        sa.ForeignKeyConstraint(['source_id','account_id'],['dismantling_catalog_sources.id','dismantling_catalog_sources.account_id'],name='fk_dcatalog_source_account'),
        sa.UniqueConstraint('source_id','catalog_key',name='uq_dcatalog_type_key'))
    op.create_index('ix_dismantling_catalog_types_account_id','dismantling_catalog_types',['account_id'])
    op.create_index('ix_dismantling_catalog_types_source_id','dismantling_catalog_types',['source_id'])


def downgrade():
    op.drop_table('dismantling_catalog_types')
    op.drop_table('dismantling_catalog_sources')
    op.drop_column('dismantling_items','included')
