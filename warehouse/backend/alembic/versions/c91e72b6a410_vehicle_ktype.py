"""Optional confirmed Plan.Parts K-Type on Warehouse donors."""
from alembic import op
import sqlalchemy as sa

revision = "c91e72b6a410"
down_revision = "f482ab1376c0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vehicles", sa.Column("ktype", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_vehicle_ktype_positive", "vehicles", "ktype IS NULL OR ktype > 0")


def downgrade():
    op.drop_constraint("ck_vehicle_ktype_positive", "vehicles", type_="check")
    op.drop_column("vehicles", "ktype")
