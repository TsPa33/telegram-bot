"""Allow bounded Aleto offline jobs and durable, private small result artifacts."""
from alembic import op
import sqlalchemy as sa
revision='d3a82f1c904b'
down_revision='c8f21d6e903a'
branch_labels=None
depends_on=None
TYPE="(source='file' AND job_type IN ('file_validation','catalogue_preview')) OR (source='aleto_fixture' AND job_type='aleto_offline')"

def upgrade():
    op.drop_constraint('ck_import_runner_type','import_jobs',type_='check')
    op.create_check_constraint('ck_import_runner_type','import_jobs',TYPE)
    op.create_table('import_job_artifacts',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('job_id',sa.String(36),sa.ForeignKey('import_jobs.id'),nullable=False,unique=True),
        sa.Column('content',sa.LargeBinary(),nullable=False),
        sa.Column('sha256',sa.String(64),nullable=False),
        sa.Column('size_bytes',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('catalogue_job_id',sa.String(36),sa.ForeignKey('catalogue_jobs.id'),nullable=True),
        sa.CheckConstraint('size_bytes BETWEEN 1 AND 1048576 AND octet_length(content)=size_bytes',name='ck_runner_artifact_size'))
    op.execute("CREATE FUNCTION runner_artifact_content_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.content IS DISTINCT FROM OLD.content OR NEW.sha256 IS DISTINCT FROM OLD.sha256 OR NEW.job_id IS DISTINCT FROM OLD.job_id OR NEW.size_bytes IS DISTINCT FROM OLD.size_bytes THEN RAISE EXCEPTION 'Runner artifact content is immutable'; END IF; RETURN NEW; END $$")
    op.execute("CREATE TRIGGER runner_artifact_content_no_change BEFORE UPDATE ON import_job_artifacts FOR EACH ROW EXECUTE FUNCTION runner_artifact_content_immutable()")

def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM import_job_artifacts) OR EXISTS(SELECT 1 FROM import_jobs WHERE job_type='aleto_offline')")):raise RuntimeError('Adapter history exists; use reviewed roll-forward')
    op.drop_table('import_job_artifacts');op.execute('DROP FUNCTION runner_artifact_content_immutable()')
    op.drop_constraint('ck_import_runner_type','import_jobs',type_='check')
    op.create_check_constraint('ck_import_runner_type','import_jobs',"source='file' AND job_type IN ('file_validation','catalogue_preview')")
