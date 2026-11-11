"""Add physical assembly evidence; no stock/backfill mutations."""
from alembic import op
import sqlalchemy as sa
revision='f7a10b8c43d2'
down_revision='e641b3a20f97'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('dismantling_items',sa.Column('assembly_completeness',sa.String(20),nullable=True))
    op.add_column('dismantling_items',sa.Column('assembly_consumed_operation_id',sa.String(36),nullable=True))
    op.create_foreign_key('fk_assembly_consumed_operation','dismantling_items','operations',['assembly_consumed_operation_id'],['id'])
    op.create_unique_constraint('uq_dismantling_assembly_scope','dismantling_items',['id','account_id','vehicle_id'])
    op.create_check_constraint('ck_assembly_completeness','dismantling_items',"assembly_completeness IS NULL OR assembly_completeness IN ('unchecked','complete','incomplete')")
    op.create_table('assembly_memberships',
        sa.Column('id',sa.String(36),primary_key=True),sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('vehicle_id',sa.String(36),nullable=False),sa.Column('parent_item_id',sa.String(36),nullable=False),sa.Column('child_item_id',sa.String(36),nullable=False),
        sa.Column('active',sa.Boolean,nullable=False,server_default='true'),sa.Column('attached_at',sa.DateTime(timezone=True),nullable=False),sa.Column('detached_at',sa.DateTime(timezone=True)),
        sa.Column('attached_operation_id',sa.String(36),sa.ForeignKey('operations.id'),nullable=False),sa.Column('detached_operation_id',sa.String(36),sa.ForeignKey('operations.id')),
        sa.ForeignKeyConstraint(['parent_item_id','account_id','vehicle_id'],['dismantling_items.id','dismantling_items.account_id','dismantling_items.vehicle_id'],name='fk_assembly_parent_scope'),
        sa.ForeignKeyConstraint(['child_item_id','account_id','vehicle_id'],['dismantling_items.id','dismantling_items.account_id','dismantling_items.vehicle_id'],name='fk_assembly_child_scope'),
        sa.CheckConstraint('parent_item_id <> child_item_id',name='ck_assembly_not_self'),
        sa.CheckConstraint('(active AND detached_at IS NULL AND detached_operation_id IS NULL) OR (NOT active AND detached_at IS NOT NULL AND detached_operation_id IS NOT NULL)',name='ck_assembly_detach_evidence'))
    for col in ('account_id','vehicle_id','parent_item_id','child_item_id'):
        op.create_index('ix_assembly_memberships_'+col,'assembly_memberships',[col])
    op.create_index('uq_assembly_active_child','assembly_memberships',['child_item_id'],unique=True,postgresql_where=sa.text('active'))
    op.create_table('assembly_templates',sa.Column('id',sa.String(36),primary_key=True),sa.Column('account_id',sa.String(36),sa.ForeignKey('accounts.id'),nullable=False),
        sa.Column('name',sa.String(200),nullable=False),sa.Column('version',sa.Integer,nullable=False),sa.Column('payload',sa.JSON,nullable=False),
        sa.Column('provenance',sa.String(2000),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint('account_id','name','version',name='uq_assembly_template_version'))
    op.create_index('ix_assembly_templates_account_id','assembly_templates',['account_id'])
    op.execute('''CREATE FUNCTION warehouse_assembly_no_cycle() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      PERFORM id FROM accounts WHERE id=NEW.account_id FOR NO KEY UPDATE;
      IF TG_OP='UPDATE' AND (OLD.parent_item_id,OLD.child_item_id,OLD.account_id,OLD.vehicle_id) IS DISTINCT FROM
          (NEW.parent_item_id,NEW.child_item_id,NEW.account_id,NEW.vehicle_id) THEN
        RAISE EXCEPTION 'assembly identity is immutable';
      END IF;
      IF TG_OP='UPDATE' AND NOT OLD.active AND NEW.active THEN RAISE EXCEPTION 'membership cannot be reactivated'; END IF;
      IF NEW.active AND EXISTS(WITH RECURSIVE descendants(id) AS (
          SELECT NEW.child_item_id UNION SELECT m.child_item_id FROM assembly_memberships m
          JOIN descendants d ON m.parent_item_id=d.id WHERE m.active AND m.account_id=NEW.account_id AND m.id<>NEW.id
      ) SELECT 1 FROM descendants WHERE id=NEW.parent_item_id) THEN RAISE EXCEPTION 'assembly cycle'; END IF;
      RETURN NEW;
    END $$''')
    op.execute('CREATE TRIGGER assembly_history_no_delete BEFORE DELETE ON assembly_memberships FOR EACH ROW EXECUTE FUNCTION warehouse_reject_audit_change()')
    op.execute('CREATE TRIGGER assembly_templates_immutable BEFORE UPDATE OR DELETE ON assembly_templates FOR EACH ROW EXECUTE FUNCTION warehouse_reject_audit_change()')
    op.execute('CREATE TRIGGER assembly_no_cycle BEFORE INSERT OR UPDATE ON assembly_memberships FOR EACH ROW EXECUTE FUNCTION warehouse_assembly_no_cycle()')

    op.execute("""CREATE FUNCTION warehouse_assembly_item_identity() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF OLD.part_id IS NOT NULL AND OLD.part_id IS DISTINCT FROM NEW.part_id AND (
        OLD.assembly_completeness IS NOT NULL OR OLD.assembly_consumed_operation_id IS NOT NULL OR EXISTS(
        SELECT 1 FROM assembly_memberships m WHERE m.parent_item_id=OLD.id OR m.child_item_id=OLD.id)) THEN
        RAISE EXCEPTION 'assembly physical identity cannot be rebound' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER assembly_item_identity BEFORE UPDATE OF part_id ON dismantling_items FOR EACH ROW EXECUTE FUNCTION warehouse_assembly_item_identity()')
    op.execute("""CREATE FUNCTION warehouse_assembly_part_identity() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF (OLD.vehicle_id,OLD.account_id) IS DISTINCT FROM (NEW.vehicle_id,NEW.account_id) AND EXISTS(
        SELECT 1 FROM dismantling_items n WHERE n.part_id=OLD.id AND (
        n.assembly_completeness IS NOT NULL OR n.assembly_consumed_operation_id IS NOT NULL OR EXISTS(
        SELECT 1 FROM assembly_memberships m WHERE m.parent_item_id=n.id OR m.child_item_id=n.id))) THEN
        RAISE EXCEPTION 'assembly part cannot change donor' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER assembly_part_identity BEFORE UPDATE OF vehicle_id,account_id ON parts FOR EACH ROW EXECUTE FUNCTION warehouse_assembly_part_identity()')


def downgrade():
    raise RuntimeError('Cannot discard assembly history; disable UI and review compatibility instead of destructive downgrade')
