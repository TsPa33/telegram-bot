from app.api.secure_route import SecureRoute
import json
import secrets
from datetime import datetime
from typing import Annotated, Literal
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session as DBSession
from app.api.deps import Identity, identity
from app.config import photo_dir, secure_cookies, registration_enabled
from app.db import get_db
from app.models import Account, Category, Operation, Part, Photo, Vehicle, VehiclePhoto
from app.schemas import (
    BulkInput,
    CategoryImport,
    Credentials,
    PartInput,
    PartCharacteristicsInput,
    PriceInput,
    Registration,
    StockInput,
    VehicleInput,
    VehiclePowertrainInput,
    VehicleSpecificationsInput,
)
from app.services import auth
from app.services.vehicle_catalog import local_catalog, automatic_donor_id
from app.services.analytics import dashboard
from app.services.inventory import (
    checklist,
    import_categories,
    owned,
    record,
    snapshot,
    stock,
    validate_part_links,
)

router = APIRouter(route_class=SecureRoute,prefix="/api/v1")
DB = Annotated[DBSession, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


def user_info(user):
    from app.services.team import user_info as info
    from app.services.catalogue_import import platform_admin
    return {**info(user), 'catalogue_platform_admin': platform_admin(user)}


def session_response(db, response, user):
    token, csrf = auth.create_session(db, user)
    from app.models import TeamEvent
    if user.workspace_account_id or db.scalar(select(Account.id).where(Account.workspace_account_id==user.id).limit(1)):
        db.add(TeamEvent(workspace_account_id=user.workspace_account_id or user.id,actor_id=user.id,target_id=user.id,type='session_started',data={}))
    db.commit()
    response.set_cookie(
        "warehouse_session",
        token,
        httponly=True,
        secure=secure_cookies(),
        samesite="strict",
        max_age=604800,
        path="/api/v1",
    )
    response.set_cookie(
        "warehouse_csrf",
        csrf,
        httponly=False,
        secure=secure_cookies(),
        samesite="strict",
        max_age=604800,
        path="/",
    )
    return {"user": user_info(user), "csrf_token": csrf}


@router.get("/auth/options", tags=["Authentication"])
def auth_options():
    return {"registration_enabled": registration_enabled()}


@router.post("/auth/register", status_code=201, tags=["Authentication"])
def register(data: Registration, request: Request, response: Response, db: DB):
    if not registration_enabled():
        raise HTTPException(
            403, "Реєстрацію вимкнено. Зверніться до власника робочого простору"
        )
    auth.throttle(("register", request.client.host if request.client else "unknown"))
    if db.scalar(select(Account).where(Account.email == data.email)):
        raise HTTPException(409, "Не вдалося створити обліковий запис із цією поштою")
    user = Account(
        email=data.email, name=data.name, password_hash=auth.hasher.hash(data.password)
    )
    db.add(user)
    db.flush()
    return session_response(db, response, user)


@router.post("/auth/login", tags=["Authentication"])
def login(data: Credentials, request: Request, response: Response, db: DB):
    auth.throttle(("login", request.client.host if request.client else "unknown"))
    user = auth.authenticate(db, data.email, data.password)
    # Rotate the current browser session rather than leaving an old credential live.
    old = request.cookies.get("warehouse_session")
    if old:
        from app.models import Session

        session = db.get(Session, auth.digest(old))
        if session:
            db.delete(session)
    return session_response(db, response, user)


@router.get("/auth/me", tags=["Authentication"])
def me(who: Auth):
    return user_info(who.user)


@router.post("/auth/logout", status_code=204, tags=["Authentication"])
def logout(response: Response, db: DB, who: Auth):
    db.delete(who.session)
    db.commit()
    response.delete_cookie(
        "warehouse_session",
        path="/api/v1",
        secure=secure_cookies(),
        httponly=True,
        samesite="strict",
    )
    response.delete_cookie(
        "warehouse_csrf", path="/", secure=secure_cookies(), samesite="strict"
    )


def vehicle_stock_counts(db, account_id, ids):
    """One account-scoped aggregate for a whole page, never per-row queries.

    A position counts when it is active and has physical quantity > 0, including
    reserved units. A potential checklist/zero balance is not stock.
    """
    return dict(db.execute(select(Part.vehicle_id, func.count(Part.id)).where(
        Part.account_id == account_id, Part.vehicle_id.in_(ids),
        Part.archived.is_(False), Part.assortment_enabled.is_(True), Part.quantity > 0).group_by(Part.vehicle_id)).all()) if ids else {}


def vehicle_view(db, row, account_id):
    return {**snapshot(row), 'stock_positions':vehicle_stock_counts(db, account_id, [row.id]).get(row.id, 0)}


def listing(
    db, model, account_id, *, q="", archived=False, offset=0, limit=100, filters=(), currency_aware=False
):
    stmt = select(model).where(
        model.account_id == account_id, model.archived == archived, *filters
    )
    if q:
        fields = (
            [model.manufacturer, model.model, model.donor_id, model.vin,
             cast(model.number, String)]
            if model is Vehicle
            else [
                model.name,
                model.oem_number,
                model.article_number,
                model.location,
                model.serial_number,
            ]
            if model is Part
            else [model.name]
        )
        stmt = stmt.where(
            or_(
                *(
                    f.ilike("%" + q.replace("%", r"\%").replace("_", r"\_") + "%")
                    for f in fields
                )
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(db.scalars(
        stmt.order_by(model.created_at.desc(), model.id).offset(offset).limit(limit)
    ))
    vehicle_counts = vehicle_stock_counts(db, account_id, [r.id for r in rows]) if model is Vehicle else {}
    items = []
    for row in rows:
        item = snapshot(row)
        if model is Vehicle:
            item["stock_positions"] = vehicle_counts.get(row.id, 0)
        if isinstance(row, Part):
            item["available_quantity"] = row.available_quantity
            if row.currency != "UAH" and not currency_aware:
                item["selling_price"] = None
                item["price_requires_currency_client"] = True
        items.append(item)
    return {"items": items, "total": total, "offset": offset, "limit": limit}


@router.get("/vehicles", tags=["Vehicles"])
def vehicles(
    db: DB,
    who: Auth,
    q: str = "",
    archived: bool = False,
    status: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    return listing(
        db,
        Vehicle,
        who.workspace_account_id,
        q=q,
        archived=archived,
        offset=offset,
        limit=limit,
        filters=[Vehicle.status == status] if status else [],
    )


@router.get("/vehicle-catalog", tags=["Vehicles"])
def vehicle_catalog(db: DB, who: Auth):
    return local_catalog(db, who.workspace_account_id)


@router.post("/vehicles", status_code=201, tags=["Vehicles"])
def vehicle_create(data: VehicleInput, db: DB, who: Auth):
    values = data.model_dump()
    if values["donor_id"] is None:
        values["donor_id"] = automatic_donor_id(db, who.workspace_account_id)
    # Serialize allocation even when callers supply their own donor_id.
    db.scalar(select(Account).where(Account.id == who.workspace_account_id).with_for_update())
    number = (db.scalar(select(func.max(Vehicle.number)).where(Vehicle.account_id == who.workspace_account_id)) or 0) + 1
    row = Vehicle(account_id=who.workspace_account_id, number=number, **values)
    db.add(row)
    record(db, who.workspace_account_id, row, "vehicle_create", "Додано донора", {})
    db.commit()
    return vehicle_view(db, row, who.workspace_account_id)


@router.get("/vehicles/{id}", tags=["Vehicles"])
def vehicle_get(id: str, db: DB, who: Auth):
    return vehicle_view(db, owned(db, Vehicle, id, who.workspace_account_id), who.workspace_account_id)


@router.put("/vehicles/{id}", tags=["Vehicles"])
def vehicle_update(id: str, data: VehicleInput, db: DB, who: Auth):
    row = owned(db, Vehicle, id, who.workspace_account_id, lock=True, active=True)
    before = snapshot(row)
    changes = data.model_dump(exclude_unset=True)
    if "donor_id" in changes and changes["donor_id"] is None:
        raise HTTPException(422, "Внутрішній ID не може бути порожнім")
    identifying = ("manufacturer", "model", "year", "engine", "generation", "fuel_type", "transmission")
    if "ktype" not in changes and any(k in changes and changes[k] != getattr(row, k) for k in identifying):
        changes["ktype"] = None
    for k, v in changes.items():
        setattr(row, k, v)
    record(db, who.workspace_account_id, row, "vehicle_update", "Оновлено донора", before)
    db.commit()
    return vehicle_view(db, row, who.workspace_account_id)


@router.patch("/vehicles/{id}/powertrain", tags=["Vehicles"])
def vehicle_powertrain(id: str, data: VehiclePowertrainInput, db: DB, who: Auth):
    row = owned(db, Vehicle, id, who.workspace_account_id, lock=True, active=True)
    before = snapshot(row)
    changes = data.model_dump(exclude_unset=True)
    if any(k in changes and changes[k]!=getattr(row,k) for k in ("engine","fuel_type")):
        row.ktype = None  # Prior provider checklist history remains intact.
    for key, value in changes.items():
        setattr(row, key, value)
    if snapshot(row) != before:
        record(db, who.workspace_account_id, row, "vehicle_update", "Оновлено двигун / КПП", before)
    db.commit()
    return vehicle_view(db, row, who.workspace_account_id)


@router.patch("/vehicles/{id}/specifications", tags=["Vehicles"])
def vehicle_specifications(id: str, data: VehicleSpecificationsInput, db: DB, who: Auth):
    """Update only supplied donor facts; never guess a trim from model or VIN."""
    row = owned(db, Vehicle, id, who.workspace_account_id, lock=True, active=True)
    before = snapshot(row)
    changes = data.model_dump(exclude_unset=True)
    if any(key in changes and changes[key] != getattr(row, key) for key in (
        "engine", "fuel_type", "engine_displacement_l", "engine_variant", "engine_code"
    )):
        row.ktype = None  # Prevent stale Plan.Parts fitment claims.
    for key, value in changes.items():
        setattr(row, key, value)
    if snapshot(row) != before:
        record(db, who.workspace_account_id, row, "vehicle_update", "Оновлено характеристики донора", before)
    db.commit()
    return vehicle_view(db, row, who.workspace_account_id)


@router.get("/vehicle-view/readiness", tags=["Vehicles"])
def vehicle_view_readiness(db: DB, who: Auth):
    from app.api.dismantling import simple_readiness
    result = simple_readiness(db, who)
    return {**result, 'contract_version':4,
            'features':result['features']+['vehicle_stock_counts','powertrain_edit']}


@router.get("/vehicles/{id}/analytics", tags=["Analytics"])
def vehicle_analytics(id: str, db: DB, who: Auth):
    owned(db, Vehicle, id, who.workspace_account_id)
    return dashboard(db, who.workspace_account_id, id)


@router.post("/vehicles/{id}/checklist", tags=["Checklists"])
def generate_checklist(id: str, db: DB, who: Auth):
    result = checklist(db, id, who.workspace_account_id)
    db.commit()
    return result


@router.get("/categories", tags=["Categories"])
def categories(
    db: DB,
    who: Auth,
    q: str = "",
    archived: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=10000),
):
    return listing(
        db, Category, who.workspace_account_id, q=q, archived=archived, offset=offset, limit=limit
    )


@router.post("/categories/import", tags=["Categories"])
def category_import(data: CategoryImport, db: DB, who: Auth, dry_run: bool = False):
    result = import_categories(db, data, who.workspace_account_id, dry_run=dry_run)
    if not dry_run:
        db.commit()
    return result


@router.post("/categories/import-file", tags=["Categories"])
async def category_file(
    db: DB, who: Auth, file: UploadFile = File(...), dry_run: bool = True
):
    raw = await file.read(4 * 1024 * 1024 + 1)
    if len(raw) > 4 * 1024 * 1024:
        raise HTTPException(413, "Файл завеликий: максимум 4 МБ")
    try:
        # Explicit UTF-8 JSON contract: do not guess a raw taxonomy's encoding/hierarchy.
        data = CategoryImport.model_validate(json.loads(raw.decode("utf-8-sig")))
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(
            422, "Потрібен UTF-8 JSON із source та nodes; перевірте формат імпорту"
        ) from exc
    result = import_categories(db, data, who.workspace_account_id, dry_run=dry_run)
    if not dry_run:
        db.commit()
    return result


@router.get("/parts", tags=["Inventory"])
@router.get("/inventory", tags=["Inventory"])
def parts(
    db: DB,
    who: Auth,
    request: Request,
    q: str = "",
    archived: bool = False,
    vehicle_id: str | None = None,
    category_id: str | None = None,
    availability: str | None = None,
    condition: str | None = None,
    location: str | None = None,
    in_stock: bool = False,
    manufacturer: str | None = Query(None,max_length=100),
    model: str | None = Query(None,max_length=100),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    filters = []
    for col, value in [
        (Part.vehicle_id, vehicle_id),
        (Part.category_id, category_id),
        (Part.availability, availability),
        (Part.condition, condition),
        (Part.location, location),
    ]:
        if value is not None:
            filters.append(col == value)
    if manufacturer is not None or model is not None:
        donors=select(Vehicle.id).where(Vehicle.account_id==who.workspace_account_id)
        if manufacturer is not None:donors=donors.where(func.lower(Vehicle.manufacturer)==manufacturer.lower())
        if model is not None:donors=donors.where(func.lower(Vehicle.model)==model.lower())
        filters.append(Part.vehicle_id.in_(donors))
    if in_stock:
        filters.extend([Part.quantity > 0, Part.assortment_enabled.is_(True)])
    return listing(
        db,
        Part,
        who.workspace_account_id,
        q=q,
        archived=archived,
        offset=offset,
        limit=limit,
        filters=filters,
        currency_aware=request.headers.get("X-Warehouse-Client")=="5",
    )


@router.post("/parts", status_code=201, tags=["Inventory"])
def part_create(data: PartInput, db: DB, who: Auth):
    validate_part_links(db, data, who.workspace_account_id)
    row = Part(account_id=who.workspace_account_id, **data.model_dump())
    db.add(row)
    record(db, who.workspace_account_id, row, "part_create", "Додано позицію без залишку", {})
    db.commit()
    return {**snapshot(row), "available_quantity": row.available_quantity}


@router.get("/parts/{id}", tags=["Inventory"])
def part_get(id: str, request: Request, db: DB, who: Auth):
    row = owned(db, Part, id, who.workspace_account_id)
    result={**snapshot(row), "available_quantity": row.available_quantity}
    # Previous UI labels every price UAH. Do not expose USD as a misleading
    # hryvnia amount to that client; the exact stored value is never changed.
    if row.currency!='UAH' and request.headers.get('X-Warehouse-Client')!='5':
        result.update(selling_price=None,price_requires_currency_client=True)
    return result


@router.put("/parts/{id}", tags=["Inventory"])
def part_update(id: str, data: PartInput, db: DB, who: Auth):
    row = owned(db, Part, id, who.workspace_account_id, lock=True, active=True)
    validate_part_links(db, data, who.workspace_account_id)
    if data.individually_tracked and row.quantity > 1:
        raise HTTPException(
            409, "Спочатку розділіть кількісну позицію на окремі одиниці"
        )
    before = snapshot(row)
    changes=data.model_dump()
    # Old full-form clients must retain newly introduced optional characteristics.
    for field in ("color_name","paint_code"):
        if field not in data.model_fields_set:changes.pop(field,None)
    if 'parts.view_cost' not in who.permissions:changes.pop('unit_cost',None)
    if 'parts.change_price' not in who.permissions:
        changes.pop('selling_price',None);changes.pop('currency',None)
    if 'parts.notes' not in who.permissions:changes.pop('internal_notes',None)
    if 'inventory.transfer' not in who.permissions:changes.pop('location',None)
    if 'vehicles.view' not in who.permissions:changes.pop('vehicle_id',None)
    if 'catalog.view' not in who.permissions:
        changes.pop('category_id',None);changes.pop('subcategory_id',None)
    if 'parts.inspect' not in who.permissions:
        changes.pop('condition',None);changes.pop('availability',None)
    if 'currency' not in data.model_fields_set:
        changes.pop('currency',None)
        if row.currency!='UAH' and changes.get('selling_price',row.selling_price)!=row.selling_price:
            raise HTTPException(409,'Підтвердіть валюту ціни в оновленій картці запчастини')
    for k, v in changes.items():
        setattr(row, k, v)
    record(db, who.workspace_account_id, row, "part_update", "Оновлено картку запчастини", before)
    db.commit()
    return {**snapshot(row), "available_quantity": row.available_quantity}


@router.patch('/parts/{id}/characteristics', tags=['Inventory'])
def part_characteristics(id: str, data: PartCharacteristicsInput, db: DB, who: Auth):
    row=owned(db,Part,id,who.workspace_account_id,lock=True,active=True)
    before=snapshot(row)
    if all(getattr(row,k)==v for k,v in data.values.items()):
        return {**before,'available_quantity':row.available_quantity}
    if any(getattr(row,k)!=v for k,v in data.expected.items()):
        raise HTTPException(409,'Характеристики вже змінено. Перечитайте картку та порівняйте значення.')
    for key,value in data.values.items():setattr(row,key,value)
    record(db,who.workspace_account_id,row,'part_update','Оновлено OEM / колір деталі',before)
    db.commit()
    return {**snapshot(row),'available_quantity':row.available_quantity}


@router.post("/parts/{id}/operations", tags=["Stock operations"])
def stock_operation(id: str, data: StockInput, db: DB, who: Auth):
    from app.models import StockRequest
    if who.user.role!='DIRECTOR' and not data.request_key:raise HTTPException(422,'Операція працівника потребує request_key')
    if data.sale_price is not None and not data.request_key:
        raise HTTPException(422,"Фінансовий продаж потребує request_key")
    from hashlib import sha256
    if data.request_key:
        # Account then Part, same lock order as donor receipts. Serializes keys
        # across different parts too, avoiding duplicate-key races.
        db.scalar(select(Account).where(Account.id==who.workspace_account_id).with_for_update())
    row = owned(db, Part, id, who.workspace_account_id, lock=True)
    # Preserve pre-UX5.6 fingerprints exactly when financial fields are absent.
    payload=data.model_dump(mode='json',exclude={'request_key','sale_price','sale_currency'})
    if data.physical_location_kind is None:payload.pop('physical_location_kind',None)
    if data.sale_price is not None:
        payload.update(sale_price=format(data.sale_price,'.2f'),sale_currency=data.sale_currency)
    fingerprint=sha256(json.dumps({'part_id':id,**payload},sort_keys=True).encode()).hexdigest()
    if data.request_key:
        prior=db.scalar(select(StockRequest).where(StockRequest.account_id==who.workspace_account_id,StockRequest.request_key==data.request_key))
        if prior:
            if prior.actor_id!=who.actor_id:raise HTTPException(409,'Ключ належить іншому виконавцю')
            if prior.fingerprint!=fingerprint:raise HTTPException(409,'Цей запит уже використано для іншої операції')
            return prior.response
    stock(db, row, data, who.workspace_account_id)
    result={**snapshot(row), 'available_quantity':row.available_quantity}
    if data.request_key:
        db.add(StockRequest(account_id=who.workspace_account_id,actor_id=who.actor_id,part_id=id,request_key=data.request_key,fingerprint=fingerprint,response=result))
    db.commit()
    return result


@router.patch('/parts/{id}/price',tags=['Inventory'])
def price_update(id: str,data: PriceInput,db: DB,who: Auth):
    from app.services import pricing
    from app.services.virtual_inventory import lock_workspace
    lock_workspace(db,who.workspace_account_id)
    row=owned(db,Part,id,who.workspace_account_id,lock=True)
    result=pricing.manual(db,row,who,data);db.commit();return result


@router.get('/sales-workspace/readiness',tags=['Inventory'])
def sales_readiness(db: DB,who: Auth):
    from app.models import StockRequest
    result=vehicle_view_readiness(db,who)
    from sqlalchemy.exc import SQLAlchemyError
    try:
        db.execute(select(Part.currency).limit(0));db.execute(select(StockRequest).limit(0))
    except SQLAlchemyError:raise HTTPException(503,'Sales workspace schema is not ready') from None
    return {**result,'contract_version':5,'features':result['features']+['currency_prices','stock_request_replay','donor_part_search']}



@router.post("/parts/bulk-actions", tags=["Inventory"])
def bulk(data: BulkInput, db: DB, who: Auth):
    from app.schemas import StockInput

    rows = [owned(db, Part, id, who.workspace_account_id, lock=True) for id in sorted(set(data.ids))]
    for row in rows:
        if data.action == "transfer":
            stock(
                db,
                row,
                StockInput(type="transfer", location=data.location, reason=data.reason),
                who.workspace_account_id,
            )
        else:
            archive_row(db, row, who.workspace_account_id, data.action == "archive", data.reason)
    db.commit()
    return {"updated": len(rows)}


def archive_row(db, row, account_id, archived, reason):
    if isinstance(row, Part) and archived and row.reserved_quantity:
        raise HTTPException(409, "Спершу зніміть резерв")
    before = snapshot(row)
    row.archived = archived
    record(db, account_id, row, "archive" if archived else "restore", reason, before)


@router.post("/archive/{entity}/{id}", tags=["Archive"])
def archive(
    entity: Literal["vehicles", "parts", "categories"],
    id: str,
    db: DB,
    who: Auth,
    restore: bool = False,
):
    row = owned(
        db,
        {"vehicles": Vehicle, "parts": Part, "categories": Category}[entity],
        id,
        who.workspace_account_id,
        lock=True,
    )
    archive_row(
        db,
        row,
        who.workspace_account_id,
        not restore,
        "Відновлено з архіву" if restore else "Архівовано",
    )
    db.commit()
    return snapshot(row)


@router.get("/archive", tags=["Archive"])
def archive_list(
    db: DB,
    who: Auth,
    entity: Literal["vehicles", "parts", "categories"] = "parts",
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    return listing(
        db,
        {"vehicles": Vehicle, "parts": Part, "categories": Category}[entity],
        who.workspace_account_id,
        archived=True,
        offset=offset,
        limit=limit,
    )


@router.get("/dashboard", tags=["Analytics"])
def dashboard_get(db: DB, who: Auth):
    return dashboard(db, who.workspace_account_id)


@router.get("/audit", tags=["Audit"])
def audit(
    db: DB,
    who: Auth,
    type: str | None = None,
    vehicle_id: str | None = None,
    part_id: str | None = None,
    actor_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
):
    stmt = select(Operation).where(Operation.account_id == who.workspace_account_id)
    for col, val in [
        (Operation.type, type),
        (Operation.vehicle_id, vehicle_id),
        (Operation.part_id, part_id),
        (Operation.actor_id, actor_id),
    ]:
        if val:
            stmt = stmt.where(col == val)
    if date_from:
        stmt = stmt.where(Operation.created_at >= date_from)
    if date_to:
        stmt = stmt.where(Operation.created_at <= date_to)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=list(db.scalars(stmt.order_by(Operation.created_at.desc(),Operation.id).offset(offset).limit(limit)))
    actors=dict(db.execute(select(Account.id,Account.name).where(Account.id.in_({r.actor_id for r in rows}),((Account.id==who.workspace_account_id)|(Account.workspace_account_id==who.workspace_account_id)))).all()) if rows else {}
    return {'items':[{**snapshot(r),'actor_name':(r.after.get('actor_identity') or {}).get('name') or actors.get(r.actor_id)} for r in rows],'total':total}



@router.get("/settings", tags=["Settings"])
def settings(who: Auth):
    return {
        "user": user_info(who.user),
        "photos_enabled": photo_dir() is not None,
        "currency": "UAH",
        "catalog_source_required": True,
    }



@router.get("/vehicles/{id}/photos", tags=["Vehicle photos"])
def vehicle_photos(id: str, db: DB, who: Auth):
    owned(db, Vehicle, id, who.workspace_account_id)
    return [
        {"id": item.id, "url": f"/api/v1/vehicle-photos/{item.id}", "created_at": item.created_at.isoformat()}
        for item in db.scalars(select(VehiclePhoto).where(
            VehiclePhoto.vehicle_id == id, VehiclePhoto.account_id == who.workspace_account_id
        ).order_by(VehiclePhoto.created_at.desc(), VehiclePhoto.id.desc()))
    ]


@router.post("/vehicles/{id}/photos", status_code=201, tags=["Vehicle photos"])
async def vehicle_photo_upload(id: str, db: DB, who: Auth, file: UploadFile = File(...)):
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError, ImageOps

    vehicle = owned(db, Vehicle, id, who.workspace_account_id, active=True, lock=True)
    folder = photo_dir()
    if folder is None:
        raise HTTPException(409, "Сховище фотографій не підключене")
    count = db.scalar(select(func.count(VehiclePhoto.id)).where(
        VehiclePhoto.vehicle_id == id, VehiclePhoto.account_id == who.workspace_account_id
    )) or 0
    if count >= 12:
        raise HTTPException(409, "Максимум 12 фотографій автомобіля")
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "Максимум 5 МБ")
    if not raw:
        raise HTTPException(422, "Порожній файл")
    try:
        with Image.open(BytesIO(raw)) as image:
            if image.format not in ("JPEG", "PNG", "WEBP") or image.width * image.height > 25000000:
                raise ValueError("Unsupported photo")
            image.verify()
        with Image.open(BytesIO(raw)) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((2200, 2200))
            out = BytesIO()
            image.save(out, format="JPEG", quality=86, optimize=True)
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise HTTPException(422, "Оберіть справжній JPEG, PNG або WebP до 25 Мп") from exc
    folder.mkdir(parents=True, exist_ok=True)
    filename = "vehicle-" + secrets.token_hex(24) + ".jpg"
    path = folder / filename
    photo = VehiclePhoto(
        account_id=who.workspace_account_id, vehicle_id=id,
        filename=filename, media_type="image/jpeg"
    )
    try:
        path.write_bytes(out.getvalue())
        db.add(photo)
        db.flush()
        operation = record(db, who.workspace_account_id, vehicle, "vehicle_photo_add", "Додано фото донора", {})
        operation.vehicle_id = id
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"id": photo.id, "url": f"/api/v1/vehicle-photos/{photo.id}"}


@router.get("/vehicle-photos/{photo_id}", tags=["Vehicle photos"])
def vehicle_photo_get(photo_id: str, db: DB, who: Auth):
    photo = db.get(VehiclePhoto, photo_id)
    folder = photo_dir()
    if not photo or photo.account_id != who.workspace_account_id or folder is None:
        raise HTTPException(404, "Фото не знайдено")
    owned(db, Vehicle, photo.vehicle_id, who.workspace_account_id)
    file_path = folder / photo.filename
    if not file_path.is_file():
        raise HTTPException(404, "Фото не знайдено")
    return FileResponse(file_path, media_type="image/jpeg", headers={
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff"
    })


@router.delete("/vehicles/{id}/photos/{photo_id}", status_code=204, tags=["Vehicle photos"])
def vehicle_photo_delete(id: str, photo_id: str, db: DB, who: Auth):
    vehicle = owned(db, Vehicle, id, who.workspace_account_id, active=True, lock=True)
    photo = db.get(VehiclePhoto, photo_id)
    if not photo or photo.vehicle_id != id or photo.account_id != who.workspace_account_id:
        raise HTTPException(404, "Фото не знайдено")
    file_path = photo_dir() / photo.filename if photo_dir() is not None else None
    db.delete(photo)
    record(db, who.workspace_account_id, vehicle, "vehicle_photo_delete", "Видалено фото донора", {"photo_id": photo_id})
    db.commit()
    if file_path is not None:
        file_path.unlink(missing_ok=True)
    return Response(status_code=204)


@router.get("/parts/{id}/photos", tags=["Photos"])
def photos(id: str, db: DB, who: Auth):
    owned(db, Part, id, who.workspace_account_id)
    return [
        {"id": p.id, "url": f"/api/v1/photos/{p.id}"}
        for p in db.scalars(
            select(Photo).where(Photo.part_id == id, Photo.account_id == who.workspace_account_id)
        )
    ]


@router.post("/parts/{id}/photos", status_code=201, tags=["Photos"])
async def photo_upload(id: str, db: DB, who: Auth, file: UploadFile = File(...)):
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError

    owned(db, Part, id, who.workspace_account_id, active=True)
    folder = photo_dir()
    if not folder:
        raise HTTPException(409, "Сховище фото не налаштоване")
    raw = await file.read(5 * 1024 * 1024 + 1)
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "Максимум 5 МБ")
    try:
        with Image.open(BytesIO(raw)) as image:
            if (
                image.format not in ("JPEG", "PNG", "WEBP")
                or image.width * image.height > 25000000
            ):
                raise ValueError("Unsupported image")
            image.verify()
    except (
        ValueError,
        OSError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
    ) as exc:
        raise HTTPException(
            422, "Потрібне коректне зображення JPEG, PNG або WebP до 25 Мп"
        ) from exc
    # Re-encode to strip metadata and reject embedded non-image payloads.
    with Image.open(BytesIO(raw)) as image:
        image = image.convert("RGB")
        output = BytesIO()
        image.save(output, format="JPEG", quality=88)
    folder.mkdir(parents=True, exist_ok=True)
    filename = secrets.token_hex(24) + ".jpg"
    path = folder / filename
    row = Photo(
        account_id=who.workspace_account_id, part_id=id, filename=filename, media_type="image/jpeg"
    )
    try:
        path.write_bytes(output.getvalue())
        db.add(row)
        parent=db.get(Part,id)
        operation=record(db,who.workspace_account_id,row,'photo_create','Додано фото',{})
        operation.part_id=id
        operation.vehicle_id=parent.vehicle_id
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"id": row.id, "url": f"/api/v1/photos/{row.id}"}


@router.get("/photos/{id}", tags=["Photos"])
def photo_get(id: str, db: DB, who: Auth):
    row = db.get(Photo, id)
    folder = photo_dir()
    if (
        not row
        or row.account_id != who.workspace_account_id
        or not folder
        or not (folder / row.filename).is_file()
    ):
        raise HTTPException(404, "Фото не знайдено")
    return FileResponse(
        folder / row.filename,
        media_type=row.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
