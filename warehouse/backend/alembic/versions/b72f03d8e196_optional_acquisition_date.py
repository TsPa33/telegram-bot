"""Unknown acquisition dates are NULL, never fabricated; preserve all existing rows."""
from alembic import op
import sqlalchemy as sa

revision = "b72f03d8e196"
down_revision = "a84d2c19e705"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("vehicles", "acquisition_date", existing_type=sa.Date(), nullable=True)


def downgrade():
    # Do not replace unknown dates with a fictitious value to satisfy old schema.
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM vehicles WHERE acquisition_date IS NULL)")).scalar():
        raise RuntimeError("Cannot downgrade: unknown acquisition dates exist; retain schema or explicitly resolve dates first")
    op.alter_column("vehicles", "acquisition_date", existing_type=sa.Date(), nullable=False)
