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
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session as DBSession
from app.api.deps import Identity, identity
from app.config import photo_dir, secure_cookies, registration_enabled
from app.db import get_db
from app.models import Account, Category, Operation, Part, Photo, Vehicle
from app.schemas import (
    BulkInput,
    CategoryImport,
    Credentials,
    PartInput,
    Registration,
    StockInput,
    VehicleInput,
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

router = APIRouter(prefix="/api/v1")
DB = Annotated[DBSession, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


def user_info(user):
    return {"id": user.id, "name": user.name, "email": user.email}


def session_response(db, response, user):
    token, csrf = auth.create_session(db, user)
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


def listing(
    db, model, account_id, *, q="", archived=False, offset=0, limit=100, filters=()
):
    stmt = select(model).where(
        model.account_id == account_id, model.archived == archived, *filters
    )
    if q:
        fields = (
            [model.manufacturer, model.model, model.donor_id, model.vin]
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
    rows = db.scalars(
        stmt.order_by(model.created_at.desc(), model.id).offset(offset).limit(limit)
    )
    items = []
    for row in rows:
        item = snapshot(row)
        if isinstance(row, Part):
            item["available_quantity"] = row.available_quantity
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
        who.user.id,
        q=q,
        archived=archived,
        offset=offset,
        limit=limit,
        filters=[Vehicle.status == status] if status else [],
    )


@router.get("/vehicle-catalog", tags=["Vehicles"])
def vehicle_catalog(db: DB, who: Auth):
    return local_catalog(db, who.user.id)


@router.post("/vehicles", status_code=201, tags=["Vehicles"])
def vehicle_create(data: VehicleInput, db: DB, who: Auth):
    values = data.model_dump()
    if values["donor_id"] is None:
        values["donor_id"] = automatic_donor_id(db, who.user.id)
    row = Vehicle(account_id=who.user.id, **values)
    db.add(row)
    record(db, who.user.id, row, "vehicle_create", "Додано донора", {})
    db.commit()
    return snapshot(row)


@router.get("/vehicles/{id}", tags=["Vehicles"])
def vehicle_get(id: str, db: DB, who: Auth):
    return snapshot(owned(db, Vehicle, id, who.user.id))


@router.put("/vehicles/{id}", tags=["Vehicles"])
def vehicle_update(id: str, data: VehicleInput, db: DB, who: Auth):
    row = owned(db, Vehicle, id, who.user.id, lock=True, active=True)
    before = snapshot(row)
    changes = data.model_dump(exclude_unset=True)
    if "donor_id" in changes and changes["donor_id"] is None:
        raise HTTPException(422, "Внутрішній ID не може бути порожнім")
    identifying = ("manufacturer", "model", "year", "engine", "generation", "fuel_type", "transmission")
    if "ktype" not in changes and any(k in changes and changes[k] != getattr(row, k) for k in identifying):
        changes["ktype"] = None
    for k, v in changes.items():
        setattr(row, k, v)
    record(db, who.user.id, row, "vehicle_update", "Оновлено донора", before)
    db.commit()
    return snapshot(row)


@router.get("/vehicles/{id}/analytics", tags=["Analytics"])
def vehicle_analytics(id: str, db: DB, who: Auth):
    owned(db, Vehicle, id, who.user.id)
    return dashboard(db, who.user.id, id)


@router.post("/vehicles/{id}/checklist", tags=["Checklists"])
def generate_checklist(id: str, db: DB, who: Auth):
    result = checklist(db, id, who.user.id)
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
        db, Category, who.user.id, q=q, archived=archived, offset=offset, limit=limit
    )


@router.post("/categories/import", tags=["Categories"])
def category_import(data: CategoryImport, db: DB, who: Auth, dry_run: bool = False):
    result = import_categories(db, data, who.user.id, dry_run=dry_run)
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
    result = import_categories(db, data, who.user.id, dry_run=dry_run)
    if not dry_run:
        db.commit()
    return result


@router.get("/parts", tags=["Inventory"])
@router.get("/inventory", tags=["Inventory"])
def parts(
    db: DB,
    who: Auth,
    q: str = "",
    archived: bool = False,
    vehicle_id: str | None = None,
    category_id: str | None = None,
    availability: str | None = None,
    condition: str | None = None,
    location: str | None = None,
    in_stock: bool = False,
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
    if in_stock:
        filters.append(Part.quantity > 0)
    return listing(
        db,
        Part,
        who.user.id,
        q=q,
        archived=archived,
        offset=offset,
        limit=limit,
        filters=filters,
    )


@router.post("/parts", status_code=201, tags=["Inventory"])
def part_create(data: PartInput, db: DB, who: Auth):
    validate_part_links(db, data, who.user.id)
    row = Part(account_id=who.user.id, **data.model_dump())
    db.add(row)
    record(db, who.user.id, row, "part_create", "Додано позицію без залишку", {})
    db.commit()
    return {**snapshot(row), "available_quantity": row.available_quantity}


@router.get("/parts/{id}", tags=["Inventory"])
def part_get(id: str, db: DB, who: Auth):
    row = owned(db, Part, id, who.user.id)
    return {**snapshot(row), "available_quantity": row.available_quantity}


@router.put("/parts/{id}", tags=["Inventory"])
def part_update(id: str, data: PartInput, db: DB, who: Auth):
    row = owned(db, Part, id, who.user.id, lock=True, active=True)
    validate_part_links(db, data, who.user.id)
    if data.individually_tracked and row.quantity > 1:
        raise HTTPException(
            409, "Спочатку розділіть кількісну позицію на окремі одиниці"
        )
    before = snapshot(row)
    for k, v in data.model_dump().items():
        setattr(row, k, v)
    record(db, who.user.id, row, "part_update", "Оновлено картку запчастини", before)
    db.commit()
    return {**snapshot(row), "available_quantity": row.available_quantity}


@router.post("/parts/{id}/operations", tags=["Stock operations"])
def stock_operation(id: str, data: StockInput, db: DB, who: Auth):
    row = owned(db, Part, id, who.user.id, lock=True)
    stock(db, row, data, who.user.id)
    db.commit()
    return {**snapshot(row), "available_quantity": row.available_quantity}


@router.post("/parts/bulk-actions", tags=["Inventory"])
def bulk(data: BulkInput, db: DB, who: Auth):
    from app.schemas import StockInput

    rows = [owned(db, Part, id, who.user.id, lock=True) for id in sorted(set(data.ids))]
    for row in rows:
        if data.action == "transfer":
            stock(
                db,
                row,
                StockInput(type="transfer", location=data.location, reason=data.reason),
                who.user.id,
            )
        else:
            archive_row(db, row, who.user.id, data.action == "archive", data.reason)
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
        who.user.id,
        lock=True,
    )
    archive_row(
        db,
        row,
        who.user.id,
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
        who.user.id,
        archived=True,
        offset=offset,
        limit=limit,
    )


@router.get("/dashboard", tags=["Analytics"])
def dashboard_get(db: DB, who: Auth):
    return dashboard(db, who.user.id)


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
    stmt = select(Operation).where(Operation.account_id == who.user.id)
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
    return {
        "items": [
            snapshot(r)
            for r in db.scalars(
                stmt.order_by(Operation.created_at.desc(), Operation.id)
                .offset(offset)
                .limit(limit)
            )
        ],
        "total": total,
    }


@router.get("/settings", tags=["Settings"])
def settings(who: Auth):
    return {
        "user": user_info(who.user),
        "photos_enabled": photo_dir() is not None,
        "currency": "UAH",
        "catalog_source_required": True,
    }


@router.get("/parts/{id}/photos", tags=["Photos"])
def photos(id: str, db: DB, who: Auth):
    owned(db, Part, id, who.user.id)
    return [
        {"id": p.id, "url": f"/api/v1/photos/{p.id}"}
        for p in db.scalars(
            select(Photo).where(Photo.part_id == id, Photo.account_id == who.user.id)
        )
    ]


@router.post("/parts/{id}/photos", status_code=201, tags=["Photos"])
async def photo_upload(id: str, db: DB, who: Auth, file: UploadFile = File(...)):
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError

    owned(db, Part, id, who.user.id, active=True)
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
        account_id=who.user.id, part_id=id, filename=filename, media_type="image/jpeg"
    )
    try:
        path.write_bytes(output.getvalue())
        db.add(row)
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
        or row.account_id != who.user.id
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
