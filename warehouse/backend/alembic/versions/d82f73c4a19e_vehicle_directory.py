"""R12 external vehicle directory, additive, isolated from donors and stock."""
from alembic import op
import sqlalchemy as sa

revision = 'd82f73c4a19e'
down_revision = 'c7e49f2a118d'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('vehicle_directory_variants',
        sa.Column('id',sa.String(64),primary_key=True),
        sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('brand',sa.String(120),nullable=False),
        sa.Column('model',sa.String(200),nullable=False),
        sa.Column('modification',sa.String(350),nullable=False),
        sa.Column('year_from',sa.Integer,nullable=True),
        sa.Column('year_to',sa.Integer,nullable=True),
        sa.Column('displacement_l',sa.Numeric(4,1),nullable=True),
        sa.Column('fuel_type',sa.String(50),nullable=True),
        sa.Column('power_kw',sa.Integer,nullable=True),
        sa.Column('power_ps',sa.Integer,nullable=True),
        sa.Column('body',sa.String(180),nullable=True),
        sa.Column('drive_type',sa.String(12),nullable=True),
        sa.Column('engine_codes',sa.JSON,nullable=False),
        sa.Column('kba_numbers',sa.JSON,nullable=False),
        sa.Column('source_sha',sa.String(64),nullable=False),
        sa.CheckConstraint('year_to IS NULL OR year_from IS NULL OR year_to >= year_from',name='ck_directory_year_range'),
        sa.CheckConstraint('displacement_l IS NULL OR (displacement_l > 0 AND displacement_l <= 12)',name='ck_directory_displacement'))
    op.create_index('ix_vehicle_directory_brand_model','vehicle_directory_variants',['account_id','brand','model'])
    op.create_index('ix_vehicle_directory_account_id','vehicle_directory_variants',['account_id'])
    op.create_index('ix_vehicle_directory_years','vehicle_directory_variants',['year_from','year_to'])
    op.create_table('vehicle_directory_imports',
        sa.Column('source_sha',sa.String(64),primary_key=True),
        sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),primary_key=True),
        sa.Column('filename',sa.String(200),nullable=False),
        sa.Column('record_count',sa.Integer,nullable=False),
        sa.Column('inserted_count',sa.Integer,nullable=False),
        sa.Column('imported_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():
    bind=op.get_bind()
    if bind.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM vehicle_directory_variants)')) or bind.scalar(sa.text('SELECT EXISTS(SELECT 1 FROM vehicle_directory_imports)')):
        raise RuntimeError('Vehicle reference data exists; backup and explicit data review required')
    op.drop_table('vehicle_directory_imports')
    op.drop_index('ix_vehicle_directory_years',table_name='vehicle_directory_variants')
    op.drop_index('ix_vehicle_directory_account_id',table_name='vehicle_directory_variants')
    op.drop_index('ix_vehicle_directory_brand_model',table_name='vehicle_directory_variants')
    op.drop_table('vehicle_directory_variants')
