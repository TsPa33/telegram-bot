"""Separate actors from workspace owners without rewriting inventory or history."""
from alembic import op
import sqlalchemy as sa
revision='b94f62d18e07'
down_revision='a73e05b9c842'
branch_labels=None
depends_on=None

def upgrade():
    op.execute("SET LOCAL lock_timeout='5s'")
    op.add_column('accounts',sa.Column('workspace_account_id',sa.String(36),nullable=True))
    op.create_foreign_key('fk_account_workspace','accounts','accounts',['workspace_account_id'],['id'])
    op.create_index('ix_accounts_workspace_account_id','accounts',['workspace_account_id'])
    op.add_column('accounts',sa.Column('role',sa.String(20),nullable=False,server_default='DIRECTOR'))
    op.add_column('accounts',sa.Column('permissions',sa.JSON(),nullable=False,server_default='[]'))
    op.add_column('accounts',sa.Column('is_active',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.add_column('accounts',sa.Column('must_change_password',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('accounts',sa.Column('last_login_at',sa.DateTime(timezone=True),nullable=True))
    op.create_check_constraint('ck_account_workspace_role','accounts',"(role='DIRECTOR' AND workspace_account_id IS NULL) OR (role IN ('ADMIN','MANAGER') AND workspace_account_id IS NOT NULL AND workspace_account_id<>id)")
    for table in ('stock_requests','order_requests'):
        op.add_column(table,sa.Column('actor_id',sa.String(36),nullable=True))
        op.execute(f'UPDATE {table} SET actor_id=account_id')
        op.alter_column(table,'actor_id',nullable=False)
        op.create_foreign_key('fk_'+table+'_actor',table,'accounts',['actor_id'],['id'])
    op.create_table('team_events',sa.Column('id',sa.String(36),primary_key=True),sa.Column('workspace_account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),sa.Column('actor_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),sa.Column('target_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),sa.Column('type',sa.String(40),nullable=False),sa.Column('data',sa.JSON(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_team_events_workspace_account_id','team_events',['workspace_account_id'])
    op.execute('CREATE TRIGGER immutable_team_events BEFORE UPDATE OR DELETE ON team_events FOR EACH ROW EXECUTE FUNCTION warehouse_reject_audit_change()')

def downgrade():
    # Refuse destructive identity rollback once any employee has been created.
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM accounts WHERE workspace_account_id IS NOT NULL) OR EXISTS(SELECT 1 FROM team_events) THEN RAISE EXCEPTION 'Cannot downgrade while employees or security events exist; preserve identities and audit'; END IF; END $$")
    op.drop_table('team_events')
    for table in ('stock_requests','order_requests'):
        op.drop_constraint('fk_'+table+'_actor',table,type_='foreignkey');op.drop_column(table,'actor_id')
    op.drop_constraint('ck_account_workspace_role','accounts',type_='check')
    op.drop_index('ix_accounts_workspace_account_id',table_name='accounts')
    op.drop_constraint('fk_account_workspace','accounts',type_='foreignkey')
    for name in ('workspace_account_id','role','permissions','is_active','must_change_password','last_login_at'):op.drop_column('accounts',name)
