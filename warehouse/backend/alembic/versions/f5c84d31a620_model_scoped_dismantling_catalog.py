"""Optional model applicability for existing account-local dismantling catalogue."""
from alembic import op
import sqlalchemy as sa
revision='f5c84d31a620'
down_revision='e4b93a2d715c'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('dismantling_catalog_types',sa.Column('applicability',sa.JSON(),nullable=True))

def downgrade():
    bind=op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM dismantling_catalog_types WHERE applicability IS NOT NULL)")):
        raise RuntimeError('Model-scoped catalogue exists; explicit review required before downgrade')
    op.drop_column('dismantling_catalog_types','applicability')
