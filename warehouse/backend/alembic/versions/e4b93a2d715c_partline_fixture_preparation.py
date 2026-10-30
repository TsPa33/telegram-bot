"""Permit explicitly synthetic PartLine queue type; no live contract/schema assumed."""
from alembic import op
import sqlalchemy as sa
revision='e4b93a2d715c'
down_revision='d3a82f1c904b'
branch_labels=None
depends_on=None
OLD="(source='file' AND job_type IN ('file_validation','catalogue_preview')) OR (source='aleto_fixture' AND job_type='aleto_offline')"

def upgrade():
    op.drop_constraint('ck_import_runner_type','import_jobs',type_='check')
    op.create_check_constraint('ck_import_runner_type','import_jobs',OLD+" OR (source='partline_fixture' AND job_type='partline_fixture')")

def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS(SELECT 1 FROM import_jobs WHERE job_type='partline_fixture')")):raise RuntimeError('PartLine fixture history exists; reviewed roll-forward required')
    op.drop_constraint('ck_import_runner_type','import_jobs',type_='check')
    op.create_check_constraint('ck_import_runner_type','import_jobs',OLD)
