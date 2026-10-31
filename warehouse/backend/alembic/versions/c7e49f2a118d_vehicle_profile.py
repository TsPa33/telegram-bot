"""R11.4.4 donor profile: additive optional engineering data and owned photo references.

No existing donor rows are modified. Legacy engine and transmission text is preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "c7e49f2a118d"
down_revision = "f5c84d31a620"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("vehicles", sa.Column("engine_displacement_l", sa.Numeric(3, 1), nullable=True))
    op.add_column("vehicles", sa.Column("engine_variant", sa.String(50), nullable=True))
    op.add_column("vehicles", sa.Column("engine_code", sa.String(80), nullable=True))
    op.add_column("vehicles", sa.Column("drive_type", sa.String(30), nullable=True))
    op.create_check_constraint("ck_vehicle_displacement_positive", "vehicles", "engine_displacement_l IS NULL OR (engine_displacement_l > 0 AND engine_displacement_l <= 12)")
    op.create_table(
        "vehicle_photos",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("account_id", sa.String(36), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("vehicle_id", sa.String(36), nullable=False),
        sa.Column("filename", sa.String(80), nullable=False),
        sa.Column("media_type", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vehicle_id", "account_id"], ["vehicles.id", "vehicles.account_id"], name="fk_vehicle_photo_owner"),
    )
    op.create_index("ix_vehicle_photos_vehicle_id", "vehicle_photos", ["vehicle_id"])
    op.create_index("ix_vehicle_photos_account_id", "vehicle_photos", ["account_id"])

def downgrade():
    bind=op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM vehicle_photos)")) or bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM vehicles WHERE engine_displacement_l IS NOT NULL OR engine_variant IS NOT NULL OR engine_code IS NOT NULL OR drive_type IS NOT NULL)")):
        raise RuntimeError("Donor photos or specification values exist; explicit backup/review required before downgrade")
    op.drop_index("ix_vehicle_photos_account_id", table_name="vehicle_photos")
    op.drop_index("ix_vehicle_photos_vehicle_id", table_name="vehicle_photos")
    op.drop_table("vehicle_photos")
    op.drop_constraint("ck_vehicle_displacement_positive", "vehicles", type_="check")
    for name in ("drive_type", "engine_code", "engine_variant", "engine_displacement_l"):
        op.drop_column("vehicles", name)
