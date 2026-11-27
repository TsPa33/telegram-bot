"""Store resumable Aleto preparation in Warehouse PostgreSQL."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'a20261127001'
down_revision = 'a20261120001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'aleto_import_runs',
        sa.Column('actor_id', sa.String(36), sa.ForeignKey('accounts.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('job_id', sa.BigInteger(), primary_key=True),
        sa.Column('cursor', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('seen', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('rejected', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('done', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        'aleto_import_batches',
        sa.Column('actor_id', sa.String(36), primary_key=True),
        sa.Column('job_id', sa.BigInteger(), primary_key=True),
        sa.Column('start_cursor', sa.BigInteger(), primary_key=True),
        sa.Column('end_cursor', sa.BigInteger(), nullable=False),
        sa.Column('catalogue_job_id', sa.String(36), sa.ForeignKey('catalogue_jobs.id', ondelete='SET NULL')),
        sa.Column('entries', JSONB(), nullable=False),
        sa.ForeignKeyConstraint(['actor_id', 'job_id'], ['aleto_import_runs.actor_id', 'aleto_import_runs.job_id'],
                                ondelete='CASCADE'),
    )


def downgrade():
    op.drop_table('aleto_import_batches')
    op.drop_table('aleto_import_runs')
