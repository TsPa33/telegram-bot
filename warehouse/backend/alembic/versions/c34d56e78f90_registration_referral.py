"""Persist registration referral intent across Billing outages; additive only."""
from alembic import op
import sqlalchemy as sa
revision='c34d56e78f90'
down_revision='b23c45d67e89'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('accounts',sa.Column('registration_referral_code',sa.String(16),nullable=True))
    op.add_column('accounts',sa.Column('registration_referral_state',sa.String(16),nullable=True))
    op.create_check_constraint('ck_account_registration_referral','accounts',"(registration_referral_code IS NULL AND registration_referral_state IS NULL) OR (registration_referral_code IS NOT NULL AND registration_referral_state IN ('pending','accepted','invalid') AND registration_referral_state IS NOT NULL)")

def downgrade():
    raise RuntimeError('Preserve canonical Billing identities and snapshots; roll forward or disable routing')
