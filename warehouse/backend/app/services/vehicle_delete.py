"""Scoped staging purge. Financial and cross-donor history requires owner review."""
import json
import logging

from fastapi import HTTPException
from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.exc import IntegrityError

from app.config import photo_dir
from app.models import Account, DismantlingItem, Operation, Part, Photo, StockRequest
from app.models import Vehicle, VehicleChecklistItem, VehiclePhoto
from app.models.assemblies import AssemblyMembership
from app.models.billing import DismantlingUsage
from app.models.dismantling_request import DismantlingRequest
from app.models.dismantling_ui import DismantlingAnnotation
from app.models.entitlements import DonorProvenance, EntitlementReturn
from app.models.orders import OrderLine, OrderReservation
from app.models.plan_parts_receipt import PlanPartsArticleReceipt
from app.models.plan_parts_response import PlanPartsResponse
from app.models.vehicle_configuration import VehicleConfiguration

log = logging.getLogger(__name__)
STAGING_LEDGER_TYPES = {
    'vehicle_create', 'vehicle_update', 'vehicle_photo_add', 'vehicle_photo_delete',
    'part_create', 'part_update', 'photo_create', 'photo_delete', 'checklist_update',
    'archive', 'restore', 'dismantling_annotation', 'dismantling_plan',
    'dismantling_receipt', 'dismantling_start', 'dismantling_status',
    'dismantling_v3_bind', 'dismantling_v3_save', 'dismantling_v3_decision', 'update',
    'unified_catalogue_save', 'receipt', 'reserve', 'release', 'correction',
    'transfer', 'write_off', 'virtual_activation', 'assembly_attach',
    'assembly_confirm', 'assembly_detach', 'assembly_identity', 'assembly_part_link',
    'assembly_containment', 'assembly_split_batch', 'assembly_component_plan',
}


def blocked():
    return HTTPException(409, 'Автомобіль має продажі, резерви, фінансові або пов’язані записи. '
                             'Збережіть історію в архіві та передайте випадок власнику для окремої перевірки.')


def purge(db, vehicle_id, account_id, actor_id):
    db.scalar(select(Account.id).where(Account.id == account_id).with_for_update())
    vehicle = db.scalar(select(Vehicle).where(Vehicle.account_id == account_id,
                                              Vehicle.id == vehicle_id).with_for_update())
    if vehicle is None:
        raise HTTPException(404, 'Запис не знайдено')

    parts = db.execute(select(Part.id, Part.account_id, Part.reserved_quantity)
                       .where(Part.vehicle_id == vehicle_id).order_by(Part.id).with_for_update()).all()
    if any(part.account_id != account_id or part.reserved_quantity for part in parts):
        raise blocked()
    part_ids = [part.id for part in parts]
    operations = db.execute(select(Operation.id, Operation.account_id, Operation.vehicle_id,
                                   Operation.part_id, Operation.type)
                            .where(or_(Operation.vehicle_id == vehicle_id, Operation.part_id.in_(part_ids)))
                            .order_by(Operation.id).with_for_update()).all()
    if any(op.account_id != account_id or op.vehicle_id not in (None, vehicle_id)
           or op.part_id is not None and op.part_id not in part_ids
           or op.type not in STAGING_LEDGER_TYPES for op in operations):
        raise blocked()
    operation_ids = [op.id for op in operations]

    protected = (
        select(OrderLine.id).where(or_(OrderLine.part_id.in_(part_ids),
                                        OrderLine.sale_operation_id.in_(operation_ids))),
        select(OrderReservation.id).where(or_(OrderReservation.part_id.in_(part_ids),
              OrderReservation.reserve_operation_id.in_(operation_ids),
              OrderReservation.release_operation_id.in_(operation_ids),
              OrderReservation.sale_operation_id.in_(operation_ids))),
        select(EntitlementReturn.id).where(EntitlementReturn.sale_id.in_(operation_ids)),
        select(DismantlingUsage.id).where(DismantlingUsage.vehicle_id == vehicle_id),
        select(PlanPartsArticleReceipt.id).where(PlanPartsArticleReceipt.vehicle_id == vehicle_id),
        select(PlanPartsResponse.id).where(PlanPartsResponse.vehicle_id == vehicle_id),
        select(DismantlingItem.id).where(DismantlingItem.part_id.in_(part_ids),
                                         DismantlingItem.vehicle_id != vehicle_id),
        select(DismantlingItem.id).where(DismantlingItem.vehicle_id == vehicle_id,
                                         DismantlingItem.part_id.is_not(None),
                                         DismantlingItem.part_id.not_in(part_ids)),
        select(DonorProvenance.part_id).where(or_(
            (DonorProvenance.vehicle_id == vehicle_id) & DonorProvenance.part_id.not_in(part_ids),
            DonorProvenance.part_id.in_(part_ids) & (DonorProvenance.vehicle_id != vehicle_id))),
        select(Photo.id).where(Photo.part_id.in_(part_ids), Photo.account_id != account_id),
    )
    if any(db.scalar(query.limit(1)) for query in protected):
        raise blocked()

    files = set(db.scalars(select(Photo.filename).where(Photo.account_id == account_id,
                                                       Photo.part_id.in_(part_ids))))
    files.update(db.scalars(select(VehiclePhoto.filename).where(
        VehiclePhoto.account_id == account_id, VehiclePhoto.vehicle_id == vehicle_id)))
    try:
        db.execute(text("SELECT set_config('warehouse.staging_vehicle_purge', :scope, true)"),
                   {'scope': json.dumps({'account_id': account_id, 'vehicle_id': vehicle_id})})
        for table in (AssemblyMembership, DismantlingAnnotation, DismantlingRequest,
                      VehicleChecklistItem, VehicleConfiguration, VehiclePhoto, DismantlingItem):
            db.execute(delete(table).where(table.account_id == account_id, table.vehicle_id == vehicle_id))
        db.execute(delete(DonorProvenance).where(DonorProvenance.workspace_id == account_id,
                   DonorProvenance.vehicle_id == vehicle_id, DonorProvenance.part_id.in_(part_ids)))
        for table in (StockRequest, Photo):
            db.execute(delete(table).where(table.account_id == account_id, table.part_id.in_(part_ids)))
        db.execute(update(Part).where(Part.account_id == account_id, Part.id.in_(part_ids))
                   .values(activation_operation_id=None))
        db.execute(delete(Operation).where(Operation.account_id == account_id,
                                           Operation.id.in_(operation_ids)))
        db.execute(delete(Part).where(Part.account_id == account_id, Part.id.in_(part_ids)))
        db.execute(delete(Vehicle).where(Vehicle.account_id == account_id, Vehicle.id == vehicle_id))
        db.add(Operation(account_id=account_id, actor_id=actor_id, entity_id=vehicle_id,
                         entity_type='vehicles', type='vehicle_delete', reason='Видалено тестового донора',
                         before={}, after={'deleted': True, 'parts_deleted': len(part_ids)}))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise blocked() from None

    folder = photo_dir()
    if folder is not None:
        for filename in files:
            path = folder / filename
            if path.resolve().parent != folder:
                continue
            if any(db.scalar(select(model.id).where(model.filename == filename).limit(1))
                   for model in (Photo, VehiclePhoto)):
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning('Unable to remove a deleted staging vehicle attachment', exc_info=True)
