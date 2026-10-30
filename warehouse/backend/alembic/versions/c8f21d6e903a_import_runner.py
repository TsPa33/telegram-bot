"""Add isolated, durable analysis jobs/events; no data backfill."""
from alembic import op
import sqlalchemy as sa
revision='c8f21d6e903a'
down_revision='b7e14d90c2f6'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('import_jobs',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),sa.Column('created_by',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('source',sa.String(20),nullable=False),sa.Column('job_type',sa.String(30),nullable=False),sa.Column('parameters',sa.JSON(),nullable=False),sa.Column('status',sa.String(12),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('started_at',sa.DateTime(timezone=True)),sa.Column('finished_at',sa.DateTime(timezone=True)),
        sa.Column('progress_current',sa.Integer(),nullable=False),sa.Column('progress_total',sa.Integer()),sa.Column('phase',sa.String(30),nullable=False),sa.Column('result_summary',sa.JSON(),nullable=False),
        sa.Column('error_code',sa.String(40)),sa.Column('error_message',sa.Text()),sa.Column('lease_owner',sa.String(36)),sa.Column('lease_until',sa.DateTime(timezone=True)),
        sa.Column('attempt_count',sa.Integer(),nullable=False),sa.Column('retry_count',sa.Integer(),nullable=False),sa.Column('event_count',sa.Integer(),nullable=False),
        sa.Column('idempotency_key',sa.String(36),nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('context_hash',sa.String(64),nullable=False),
        sa.UniqueConstraint('account_id','idempotency_key',name='uq_import_runner_request'),
        sa.CheckConstraint("source='file' AND job_type IN ('file_validation','catalogue_preview')",name='ck_import_runner_type'),
        sa.CheckConstraint("status <> 'running' OR (lease_owner IS NOT NULL AND lease_until IS NOT NULL)",name='ck_import_runner_lease'),
        sa.CheckConstraint("status IN ('queued','running','completed','failed','cancelled')",name='ck_import_runner_status'),
        sa.CheckConstraint('attempt_count BETWEEN 0 AND 3 AND retry_count BETWEEN 0 AND 3 AND event_count>=0 AND progress_current>=0 AND (progress_total IS NULL OR progress_total>=progress_current)',name='ck_import_runner_bounds'))
    op.create_index('ix_import_jobs_account_id','import_jobs',['account_id']);op.create_index('ix_import_jobs_created_at','import_jobs',['created_at'])
    op.create_index('uq_import_runner_active','import_jobs',['account_id','context_hash'],unique=True,postgresql_where=sa.text("status IN ('queued','running')"))
    op.create_table('import_job_events',sa.Column('id',sa.String(36),primary_key=True),sa.Column('job_id',sa.String(36),sa.ForeignKey('import_jobs.id'),nullable=False),sa.Column('sequence',sa.Integer(),nullable=False),
        sa.Column('event_type',sa.String(30),nullable=False),sa.Column('message',sa.String(500),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('metadata',sa.JSON(),nullable=False),sa.Column('request_key',sa.String(36)),
        sa.UniqueConstraint('job_id','sequence',name='uq_import_runner_event'),sa.UniqueConstraint('job_id','request_key',name='uq_import_runner_command'))
    op.create_index('ix_import_job_events_job_id','import_job_events',['job_id'])
    op.execute("CREATE FUNCTION runner_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Runner events are immutable'; END $$")
    op.execute("CREATE TRIGGER runner_events_no_change BEFORE UPDATE OR DELETE ON import_job_events FOR EACH ROW EXECUTE FUNCTION runner_events_immutable()")

def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS(SELECT 1 FROM import_jobs)')):raise RuntimeError('Runner history exists; use a reviewed roll-forward')
    op.drop_table('import_job_events');op.drop_table('import_jobs');op.execute('DROP FUNCTION runner_events_immutable()')
