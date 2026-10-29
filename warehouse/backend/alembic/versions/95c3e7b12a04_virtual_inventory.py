"""Additive virtual inventory metadata; no stock activation or data backfill."""
from alembic import op
import sqlalchemy as sa
revision='95c3e7b12a04'
down_revision='84d2c6fa190b'
branch_labels=None
depends_on=None

def upgrade():
    for name,typ,default in [('assortment_enabled',sa.Boolean(),'true'),('inventory_origin',sa.String(20),"'legacy'"),('quantity_basis',sa.String(20),"'legacy'"),('physical_location_kind',sa.String(20),"'unknown'")]:
        op.add_column('parts',sa.Column(name,typ,nullable=False,server_default=sa.text(default)))
    op.add_column('parts',sa.Column('canonical_placement_id',sa.String(36),nullable=True))
    op.add_column('parts',sa.Column('activation_operation_id',sa.String(36),nullable=True))
    op.create_foreign_key('fk_parts_canonical_placement_id_canonical_placements','parts','canonical_placements',['canonical_placement_id'],['id'])
    op.create_foreign_key('fk_part_activation_operation','parts','operations',['activation_operation_id'],['id'])
    op.create_unique_constraint('uq_parts_activation_operation_id','parts',['activation_operation_id'])
    op.create_index('uq_part_canonical_donor','parts',['account_id','vehicle_id','canonical_placement_id'],unique=True,postgresql_where=sa.text('canonical_placement_id IS NOT NULL'))
    # Initial schema used an unnamed condition CHECK; identify it by definition,
    # never drop another constraint or mutate historical condition values.
    bind=op.get_bind()
    names=bind.execute(sa.text("SELECT conname FROM pg_constraint WHERE conrelid='parts'::regclass AND contype='c' AND pg_get_constraintdef(oid) LIKE '%condition%'" )).scalars().all()
    for name in names:op.drop_constraint(name,'parts',type_='check')
    for name,expr in [('ck_part_condition',"condition IN ('unknown','used','new','damaged','refurbished')"),('ck_part_origin',"inventory_origin IN ('legacy','manual','virtual_donor')"),('ck_part_basis',"quantity_basis IN ('legacy','assumed','verified')"),('ck_part_location_kind',"physical_location_kind IN ('unknown','on_vehicle','on_shelf')")]:op.create_check_constraint(name,'parts',expr)
    op.drop_constraint('ck_dismantling_receipt_link','dismantling_items',type_='check')
    op.create_check_constraint('ck_dismantling_receipt_link','dismantling_items','received_at IS NULL OR part_id IS NOT NULL')
    op.execute('ALTER TABLE dismantling_items ADD CONSTRAINT fk_dismantling_part_account FOREIGN KEY (part_id,account_id) REFERENCES parts(id,account_id) NOT VALID')
    op.execute('ALTER TABLE dismantling_items VALIDATE CONSTRAINT fk_dismantling_part_account')

def downgrade():
    bind=op.get_bind()
    if bind.scalar(sa.text("SELECT EXISTS(SELECT 1 FROM parts WHERE inventory_origin='virtual_donor' OR activation_operation_id IS NOT NULL OR condition='unknown' OR NOT assortment_enabled OR physical_location_kind<>'unknown') OR EXISTS(SELECT 1 FROM dismantling_items WHERE part_id IS NOT NULL AND received_at IS NULL)")):
        raise RuntimeError('Virtual inventory is in use: reviewed roll-forward required; downgrade forbidden')
    op.drop_constraint('fk_dismantling_part_account','dismantling_items',type_='foreignkey')
    op.drop_constraint('ck_dismantling_receipt_link','dismantling_items',type_='check')
    op.create_check_constraint('ck_dismantling_receipt_link','dismantling_items',"(received_at IS NULL AND part_id IS NULL) OR (received_at IS NOT NULL AND part_id IS NOT NULL)")
    for name in ('ck_part_condition','ck_part_origin','ck_part_basis','ck_part_location_kind'):op.drop_constraint(name,'parts',type_='check')
    op.create_check_constraint('parts_condition_check','parts',"condition IN ('used','new','damaged','refurbished')")
    op.drop_index('uq_part_canonical_donor',table_name='parts')
    op.drop_constraint('fk_part_activation_operation','parts',type_='foreignkey')
    op.drop_constraint('fk_parts_canonical_placement_id_canonical_placements','parts',type_='foreignkey')
    op.drop_constraint('uq_parts_activation_operation_id','parts',type_='unique')
    for name in ('assortment_enabled','inventory_origin','quantity_basis','physical_location_kind','canonical_placement_id','activation_operation_id'):op.drop_column('parts',name)
