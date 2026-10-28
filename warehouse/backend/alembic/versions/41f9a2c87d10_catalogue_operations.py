"""Durable explicitly requested catalogue operations; no data import/backfill."""
from alembic import op
import sqlalchemy as sa
revision='41f9a2c87d10'
down_revision='021e8f6f220c'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('catalogue_operations',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('job_id',sa.String(36),sa.ForeignKey('catalogue_jobs.id'),nullable=False),
        sa.Column('actor_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('session_hash',sa.String(64),nullable=False),
        sa.Column('kind',sa.String(10),nullable=False),
        sa.Column('status',sa.String(10),nullable=False),
        sa.Column('command',sa.JSON(),nullable=False),
        sa.Column('progress',sa.JSON(),nullable=False),
        sa.Column('error',sa.Text(),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('finished_at',sa.DateTime(timezone=True),nullable=True),
        sa.CheckConstraint("kind IN ('preview','apply')",name='ck_catalogue_operation_kind'),
        sa.CheckConstraint("status IN ('queued','running','done','error')",name='ck_catalogue_operation_status'))
    op.create_index('ix_catalogue_operations_job_id','catalogue_operations',['job_id'])
    op.create_index('uq_catalogue_active_operation','catalogue_operations',['job_id'],unique=True,
        postgresql_where=sa.text("status IN ('queued','running')"))

def downgrade():
    op.drop_table('catalogue_operations')
