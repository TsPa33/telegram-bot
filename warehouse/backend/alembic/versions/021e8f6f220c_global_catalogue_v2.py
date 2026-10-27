"""global catalogue v2 and durable owner import jobs"""
from alembic import op
import sqlalchemy as sa

revision = '021e8f6f220c'
down_revision = 'b8716962f6b8'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('catalogue_entities',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('parent_id', sa.String(length=36), nullable=True),
    sa.Column('parent_kind', sa.String(length=20), nullable=True),
    sa.Column('name', sa.String(length=1000), nullable=False),
    sa.Column('normalized_name', sa.String(length=1000), nullable=False),
    sa.Column('identity_key', sa.String(length=64), nullable=False),
    sa.Column('details', sa.JSON(), nullable=False),
    sa.CheckConstraint("(kind IN ('manufacturer','category') AND parent_id IS NULL AND parent_kind IS NULL) OR (parent_id IS NOT NULL AND ((kind='model' AND parent_kind='manufacturer') OR (kind='subcategory' AND parent_kind='category') OR (kind='part_type' AND parent_kind='subcategory')))", name='ck_catalogue_hierarchy'),
    sa.ForeignKeyConstraint(['parent_id', 'parent_kind'], ['catalogue_entities.id', 'catalogue_entities.kind'], name='fk_catalogue_entity_parent'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'kind', name='uq_catalogue_entity_kind'),
    sa.UniqueConstraint('identity_key')
    )
    op.create_index(op.f('ix_catalogue_entities_kind'), 'catalogue_entities', ['kind'], unique=False)
    op.create_index(op.f('ix_catalogue_entities_parent_id'), 'catalogue_entities', ['parent_id'], unique=False)
    op.create_table('catalogue_sources',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('catalogue_state',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('revision', sa.Integer(), nullable=False),
    sa.CheckConstraint('id=1 AND revision>=0', name='ck_catalogue_state'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('catalogue_aliases',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('context_id', sa.String(length=36), nullable=False),
    sa.Column('alias_key', sa.String(length=64), nullable=False),
    sa.Column('source_name', sa.String(length=1000), nullable=False),
    sa.Column('target_id', sa.String(length=36), nullable=False),
    sa.Column('verified_by', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['target_id', 'kind'], ['catalogue_entities.id', 'catalogue_entities.kind'], name='fk_catalogue_alias_kind'),
    sa.ForeignKeyConstraint(['verified_by'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('kind', 'context_id', 'alias_key', name='uq_catalogue_alias')
    )
    op.create_table('catalogue_jobs',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('actor_id', sa.String(length=36), nullable=False),
    sa.Column('filename', sa.String(length=200), nullable=False),
    sa.Column('file_sha256', sa.String(length=64), nullable=False),
    sa.Column('payload_sha256', sa.String(length=64), nullable=False),
    sa.Column('rows', sa.JSON(), nullable=False),
    sa.Column('format', sa.String(length=20), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('resolutions', sa.JSON(), nullable=False),
    sa.Column('report', sa.JSON(), nullable=False),
    sa.Column('preview_token', sa.String(length=64), nullable=True),
    sa.Column('catalogue_revision', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('applied_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('uploaded','review','ready','applied','failed')", name='ck_catalogue_job_status'),
    sa.ForeignKeyConstraint(['actor_id'], ['accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_catalogue_jobs_actor_id'), 'catalogue_jobs', ['actor_id'], unique=False)
    op.create_index(op.f('ix_catalogue_jobs_file_sha256'), 'catalogue_jobs', ['file_sha256'], unique=False)
    op.create_table('catalogue_offers',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('source_id', sa.String(length=36), nullable=False),
    sa.Column('source_article', sa.String(length=150), nullable=False),
    sa.Column('properties', sa.JSON(), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['source_id'], ['catalogue_sources.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_id', 'source_article', name='uq_catalogue_source_article')
    )
    op.create_index(op.f('ix_catalogue_offers_source_id'), 'catalogue_offers', ['source_id'], unique=False)
    op.create_table('catalogue_applications',
    sa.Column('offer_id', sa.String(length=36), nullable=False),
    sa.Column('model_id', sa.String(length=36), nullable=False),
    sa.Column('model_kind', sa.String(length=20), nullable=False),
    sa.CheckConstraint("model_kind='model'", name='ck_catalogue_model_kind'),
    sa.ForeignKeyConstraint(['model_id', 'model_kind'], ['catalogue_entities.id', 'catalogue_entities.kind'], name='fk_catalogue_application_model'),
    sa.ForeignKeyConstraint(['offer_id'], ['catalogue_offers.id'], ),
    sa.PrimaryKeyConstraint('offer_id', 'model_id')
    )
    op.create_index(op.f('ix_catalogue_applications_model_id'), 'catalogue_applications', ['model_id'], unique=False)
    op.create_table('catalogue_prices',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('offer_id', sa.String(length=36), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('price_uah', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('price_usd', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('source_url', sa.Text(), nullable=False),
    sa.CheckConstraint('price_uah IS NULL OR price_uah >= 0', name='ck_catalogue_uah'),
    sa.CheckConstraint('price_usd IS NULL OR price_usd >= 0', name='ck_catalogue_usd'),
    sa.ForeignKeyConstraint(['offer_id'], ['catalogue_offers.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('offer_id', 'observed_at', name='uq_catalogue_observation')
    )
    op.create_index(op.f('ix_catalogue_prices_offer_id'), 'catalogue_prices', ['offer_id'], unique=False)
    op.create_table('catalogue_paths',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('offer_id', sa.String(length=36), nullable=False),
    sa.Column('model_id', sa.String(length=36), nullable=False),
    sa.Column('part_type_id', sa.String(length=36), nullable=True),
    sa.Column('part_kind', sa.String(length=20), nullable=True),
    sa.Column('path_key', sa.String(length=64), nullable=False),
    sa.Column('raw', sa.JSON(), nullable=False),
    sa.CheckConstraint("(part_type_id IS NULL AND part_kind IS NULL) OR (part_type_id IS NOT NULL AND part_kind='part_type')", name='ck_catalogue_path_type'),
    sa.ForeignKeyConstraint(['offer_id', 'model_id'], ['catalogue_applications.offer_id', 'catalogue_applications.model_id'], name='fk_catalogue_path_application'),
    sa.ForeignKeyConstraint(['part_type_id', 'part_kind'], ['catalogue_entities.id', 'catalogue_entities.kind'], name='fk_catalogue_path_type'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('offer_id', 'model_id', 'path_key', name='uq_catalogue_path')
    )
    op.create_index(op.f('ix_catalogue_paths_model_id'), 'catalogue_paths', ['model_id'], unique=False)
    op.create_index(op.f('ix_catalogue_paths_offer_id'), 'catalogue_paths', ['offer_id'], unique=False)
    op.create_index(op.f('ix_catalogue_paths_part_type_id'), 'catalogue_paths', ['part_type_id'], unique=False)
    op.execute("""CREATE FUNCTION catalogue_reject_price_change() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Catalogue price observations are immutable'; END; $$""")
    op.execute("""CREATE TRIGGER catalogue_immutable_price BEFORE UPDATE OR DELETE ON catalogue_prices
    FOR EACH ROW EXECUTE FUNCTION catalogue_reject_price_change()""")
    op.execute("INSERT INTO catalogue_state (id,revision) VALUES (1,0)")

def downgrade():
    op.drop_index(op.f('ix_catalogue_paths_part_type_id'), table_name='catalogue_paths')
    op.drop_index(op.f('ix_catalogue_paths_offer_id'), table_name='catalogue_paths')
    op.drop_index(op.f('ix_catalogue_paths_model_id'), table_name='catalogue_paths')
    op.drop_table('catalogue_paths')
    op.drop_index(op.f('ix_catalogue_prices_offer_id'), table_name='catalogue_prices')
    op.drop_table('catalogue_prices')
    op.execute('DROP FUNCTION catalogue_reject_price_change()')
    op.drop_index(op.f('ix_catalogue_applications_model_id'), table_name='catalogue_applications')
    op.drop_table('catalogue_applications')
    op.drop_index(op.f('ix_catalogue_offers_source_id'), table_name='catalogue_offers')
    op.drop_table('catalogue_offers')
    op.drop_index(op.f('ix_catalogue_jobs_file_sha256'), table_name='catalogue_jobs')
    op.drop_index(op.f('ix_catalogue_jobs_actor_id'), table_name='catalogue_jobs')
    op.drop_table('catalogue_jobs')
    op.drop_table('catalogue_aliases')
    op.drop_table('catalogue_state')
    op.drop_table('catalogue_sources')
    op.drop_index(op.f('ix_catalogue_entities_parent_id'), table_name='catalogue_entities')
    op.drop_index(op.f('ix_catalogue_entities_kind'), table_name='catalogue_entities')
    op.drop_table('catalogue_entities')
