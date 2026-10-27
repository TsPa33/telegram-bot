"""aleto reference catalogue v1"""
from alembic import op
import sqlalchemy as sa

revision = 'b8716962f6b8'
down_revision = 'b94f62d18e07'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('aleto_models',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('manufacturer', sa.String(length=100), nullable=False),
    sa.Column('model', sa.String(length=100), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'manufacturer', 'model'),
    sa.UniqueConstraint('id', 'account_id')
    )
    op.create_index(op.f('ix_aleto_models_account_id'), 'aleto_models', ['account_id'], unique=False)
    op.create_table('aleto_offers',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('source', sa.String(length=20), nullable=False),
    sa.Column('source_article', sa.String(length=150), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('oem', sa.Text(), nullable=True),
    sa.Column('condition', sa.Text(), nullable=False),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("source = 'aleto'"),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'source', 'source_article'),
    sa.UniqueConstraint('id', 'account_id')
    )
    op.create_index(op.f('ix_aleto_offers_account_id'), 'aleto_offers', ['account_id'], unique=False)
    op.create_table('aleto_applications',
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('offer_id', sa.String(length=36), nullable=False),
    sa.Column('model_id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['model_id', 'account_id'], ['aleto_models.id', 'aleto_models.account_id'], ),
    sa.ForeignKeyConstraint(['offer_id', 'account_id'], ['aleto_offers.id', 'aleto_offers.account_id'], ),
    sa.PrimaryKeyConstraint('account_id', 'offer_id', 'model_id')
    )
    op.create_index(op.f('ix_aleto_applications_model_id'), 'aleto_applications', ['model_id'], unique=False)
    op.create_table('aleto_prices',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('offer_id', sa.String(length=36), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('price_uah', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('price_usd', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.CheckConstraint('price_uah IS NULL OR price_uah >= 0'),
    sa.CheckConstraint('price_usd IS NULL OR price_usd >= 0'),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['offer_id', 'account_id'], ['aleto_offers.id', 'aleto_offers.account_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('offer_id', 'observed_at')
    )
    op.create_index(op.f('ix_aleto_prices_account_id'), 'aleto_prices', ['account_id'], unique=False)
    op.create_index(op.f('ix_aleto_prices_offer_id'), 'aleto_prices', ['offer_id'], unique=False)
    op.create_table('aleto_taxonomy',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('account_id', sa.String(length=36), nullable=False),
    sa.Column('offer_id', sa.String(length=36), nullable=False),
    sa.Column('model_id', sa.String(length=36), nullable=False),
    sa.Column('category_id', sa.String(length=36), nullable=False),
    sa.Column('subcategory_id', sa.String(length=36), nullable=True),
    sa.Column('raw_category', sa.String(length=200), nullable=False),
    sa.Column('raw_subcategory', sa.String(length=200), nullable=False),
    sa.Column('normalization_status', sa.String(length=20), nullable=False),
    sa.CheckConstraint("(normalization_status = 'verified' AND subcategory_id IS NOT NULL) OR (normalization_status = 'pending' AND subcategory_id IS NULL)"),
    sa.ForeignKeyConstraint(['account_id', 'offer_id', 'model_id'], ['aleto_applications.account_id', 'aleto_applications.offer_id', 'aleto_applications.model_id'], ),
    sa.ForeignKeyConstraint(['account_id'], ['accounts.id'], ),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
    sa.ForeignKeyConstraint(['subcategory_id'], ['categories.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('account_id', 'offer_id', 'model_id', 'raw_category', 'raw_subcategory')
    )
    op.create_index(op.f('ix_aleto_taxonomy_account_id'), 'aleto_taxonomy', ['account_id'], unique=False)
    op.create_index(op.f('ix_aleto_taxonomy_model_id'), 'aleto_taxonomy', ['model_id'], unique=False)
    op.create_index(op.f('ix_aleto_taxonomy_offer_id'), 'aleto_taxonomy', ['offer_id'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_aleto_taxonomy_offer_id'), table_name='aleto_taxonomy')
    op.drop_index(op.f('ix_aleto_taxonomy_model_id'), table_name='aleto_taxonomy')
    op.drop_index(op.f('ix_aleto_taxonomy_account_id'), table_name='aleto_taxonomy')
    op.drop_table('aleto_taxonomy')
    op.drop_index(op.f('ix_aleto_prices_offer_id'), table_name='aleto_prices')
    op.drop_index(op.f('ix_aleto_prices_account_id'), table_name='aleto_prices')
    op.drop_table('aleto_prices')
    op.drop_index(op.f('ix_aleto_applications_model_id'), table_name='aleto_applications')
    op.drop_table('aleto_applications')
    op.drop_index(op.f('ix_aleto_offers_account_id'), table_name='aleto_offers')
    op.drop_table('aleto_offers')
    op.drop_index(op.f('ix_aleto_models_account_id'), table_name='aleto_models')
    op.drop_table('aleto_models')
