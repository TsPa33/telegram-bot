"""Allow partial VIN registration, preserving all existing donor rows.

Only schema changes; no backfill, replacement, or inference of vehicle facts.
"""
from alembic import op
import sqlalchemy as sa

revision = "c42e1109a001"
down_revision = "c34d56e78f90"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("vehicles", "year", existing_type=sa.Integer(), nullable=True)
    op.alter_column("vehicles", "engine_displacement_l",
                    existing_type=sa.Numeric(3, 1), type_=sa.Numeric(4, 1),
                    existing_nullable=True)


def downgrade():
    conn = op.get_bind()
    if conn.scalar(sa.text("SELECT EXISTS (SELECT 1 FROM vehicles WHERE year IS NULL)")):
        raise RuntimeError("Cannot downgrade: vehicles with unknown production year exist")
    if conn.scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM vehicles WHERE engine_displacement_l > 12.0)"
    )):
        raise RuntimeError("Cannot downgrade: engine displacements above previous limit exist")
    op.alter_column("vehicles", "engine_displacement_l",
                    existing_type=sa.Numeric(4, 1), type_=sa.Numeric(3, 1),
                    existing_nullable=True)
    op.alter_column("vehicles", "year", existing_type=sa.Integer(), nullable=False)
