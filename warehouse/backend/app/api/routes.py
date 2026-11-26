from app.api.secure_route import SecureRoute
import json
import secrets
from datetime import datetime, timezone
from typing import Annotated, Literal
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Header,
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
from app.config import photo_dir, secure_cookies, registration_enabled, vehicle_delete_enabled
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
    VinClarifications,
    VinSourceIdentity,
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
    from app.services import global_billing as finance
    from app.api.deps import lock_workspace
    import os
    invite = data.referral_code if finance.enabled() and os.getenv("WAREHOUSE_REFERRALS_TEST_ENABLED") == "true" and os.getenv("WAREHOUSE_BILLING_ENVIRONMENT") == "sandbox" else None
    user = Account(
        email=data.email, name=data.name, password_hash=auth.hasher.hash(data.password),
        registration_referral_code=invite, registration_referral_state="pending" if invite else None,
    )
    db.add(user)
    db.flush()
    result = session_response(db, response, user)
    # Commit the real registration before calling a remote service. A temporary
    # outage cannot lose the account or its referral intent.
    if finance.enabled() and os.getenv("WAREHOUSE_BILLING_ENVIRONMENT") == "sandbox":
        result["billing_onboarding"] = True
        try:
            lock_workspace(db, user.id)
            who = Identity(user, None, user.id, user.id, frozenset())
            finance.ensure_onboarding(db, who)
        except HTTPException:
            db.rollback()
    return result


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


def vehicle_part_counts(db,account_id,ids):
    if not ids:return {}
    return {vehicle:(physical,registered) for vehicle,physical,registered in db.execute(
        select(Part.vehicle_id,func.count(Part.id).filter(Part.quantity>0),func.count(Part.id)).where(
            Part.account_id==account_id,Part.vehicle_id.in_(ids),Part.archived.is_(False),Part.assortment_enabled.is_(True)
        ).group_by(Part.vehicle_id))}

def vehicle_stock_counts(db,account_id,ids):return {k:v[0] for k,v in vehicle_part_counts(db,account_id,ids).items()}
def vehicle_registered_part_counts(db,account_id,ids):return {k:v[1] for k,v in vehicle_part_counts(db,account_id,ids).items()}
def vehicle_view(db,row,account_id):
    physical,registered=vehicle_part_counts(db,account_id,[row.id]).get(row.id,(0,0))
    return {**snapshot(row),'stock_positions':physical,'registered_parts':registered}


def listing(
    db, model, account_id, *, q="", archived=False, offset=0, limit=100, filters=(), currency_aware=False, category_filters=(), category_facets=False
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
                model.article_brand,
                model.description,
                model.location,
                model.serial_number,
            ]
            if model is Part
            else [model.name]
        )
        pattern="%" + q.replace("%", r"\%").replace("_", r"\_") + "%"
        expressions=[f.ilike(pattern) for f in fields]
        if model is Part:
            from app.models import VehicleChecklistItem
            original=select(VehicleChecklistItem.id).where(
                VehicleChecklistItem.account_id==account_id,VehicleChecklistItem.vehicle_id==Part.vehicle_id,
                Part.compatibility_notes==func.concat('plan.parts:ktype=',cast(VehicleChecklistItem.ktype,String),';pt_id=',cast(VehicleChecklistItem.pt_id,String)),
                or_(VehicleChecklistItem.name_en.ilike(pattern),VehicleChecklistItem.name_uk.ilike(pattern))).exists()
            expressions.append(original)
        stmt=stmt.where(or_(*expressions))
    facets = None
    if category_facets and model is Part:
        # Same account, search, stock and donor filters as the inventory query;
        # category navigation never counts just the visible page.
        facet_stmt=stmt.with_only_columns(Part.category_id,Part.subcategory_id,func.count(Part.id)).group_by(Part.category_id,Part.subcategory_id)
        facets=[dict(category_id=cat,subcategory_id=sub,count=count) for cat,sub,count in db.execute(facet_stmt)]
    if category_filters:
        stmt=stmt.where(*category_filters)
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = list(db.scalars(
        stmt.order_by(model.created_at.desc(), model.id).offset(offset).limit(limit)
    ))
    combined_counts=vehicle_part_counts(db,account_id,[r.id for r in rows]) if model is Vehicle else {}
    vehicle_counts={k:v[0] for k,v in combined_counts.items()}
    registered_counts={k:v[1] for k,v in combined_counts.items()}
    items = []
    for row in rows:
        item = snapshot(row)
        if model is Vehicle:
            item["stock_positions"] = vehicle_counts.get(row.id, 0)
            item["registered_parts"] = registered_counts.get(row.id, 0)
        if isinstance(row, Part):
            item["available_quantity"] = row.available_quantity
            if row.currency != "UAH" and not currency_aware:
                item["selling_price"] = None
                item["price_requires_currency_client"] = True
        items.append(item)
    result={"items": items, "total": total, "offset": offset, "limit": limit}
    if facets is not None: result["category_facets"]=facets
    return result


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



@router.get("/vehicle-directory/stats", tags=["Vehicle directory"])
def directory_stats(db: DB,who: Auth):
    from app.models.vehicle_directory import VehicleDirectoryVariant, VehicleDirectoryImport
    return {
        "variants": db.scalar(select(func.count()).select_from(VehicleDirectoryVariant).where(VehicleDirectoryVariant.account_id==who.workspace_account_id)) or 0,
        "brands": db.scalar(select(func.count(func.distinct(VehicleDirectoryVariant.brand))).where(VehicleDirectoryVariant.account_id==who.workspace_account_id)) or 0,
        "models": db.scalar(select(func.count()).select_from(
            select(VehicleDirectoryVariant.brand,VehicleDirectoryVariant.model).where(VehicleDirectoryVariant.account_id==who.workspace_account_id).distinct().subquery())) or 0,
        "imports": db.scalar(select(func.count()).select_from(VehicleDirectoryImport).where(VehicleDirectoryImport.account_id==who.workspace_account_id)) or 0,
        "source": "FileDbBMG / manual upload",
        "verified_current": False,
    }


@router.get("/vehicle-directory/brands", tags=["Vehicle directory"])
def directory_brands(db: DB,who: Auth):
    from app.models.vehicle_directory import VehicleDirectoryVariant
    return db.scalars(select(VehicleDirectoryVariant.brand).where(VehicleDirectoryVariant.account_id==who.workspace_account_id).distinct().order_by(VehicleDirectoryVariant.brand)).all()


@router.get("/vehicle-directory/models", tags=["Vehicle directory"])
def directory_models(db: DB,who: Auth,brand: str=Query(...,min_length=1,max_length=120)):
    from app.models.vehicle_directory import VehicleDirectoryVariant
    return db.scalars(select(VehicleDirectoryVariant.model).where(
        VehicleDirectoryVariant.account_id==who.workspace_account_id,func.lower(VehicleDirectoryVariant.brand)==brand.lower()).distinct().order_by(VehicleDirectoryVariant.model)).all()


@router.get("/vehicle-directory/variants", tags=["Vehicle directory"])
def directory_variants(
    db: DB,who: Auth,
    brand: str=Query(...,min_length=1,max_length=120),
    model: str=Query(...,min_length=1,max_length=200),
    year: int|None=Query(None,ge=1886,le=2100),
):
    from app.models.vehicle_directory import VehicleDirectoryVariant
    stmt=select(VehicleDirectoryVariant).where(VehicleDirectoryVariant.account_id==who.workspace_account_id,func.lower(VehicleDirectoryVariant.brand)==brand.lower(),VehicleDirectoryVariant.model==model)
    if year is not None:
        stmt=stmt.where(VehicleDirectoryVariant.year_from<=year).where(
            (VehicleDirectoryVariant.year_to>=year)|(VehicleDirectoryVariant.year_to.is_(None)))
    rows=db.scalars(stmt.order_by(VehicleDirectoryVariant.year_from.desc(),VehicleDirectoryVariant.modification).limit(200)).all()
    return [{"id":r.id,"modification":r.modification,"year_from":r.year_from,"year_to":r.year_to,
             "year_verified":year is not None and r.year_to is not None and r.year_from is not None and r.year_from<=year<=r.year_to,
             "displacement_l":str(r.displacement_l) if r.displacement_l is not None else None,
             "fuel_type":r.fuel_type,"power_kw":r.power_kw,"power_ps":r.power_ps,
             "drive_type":r.drive_type,"body":r.body,"engine_codes":r.engine_codes,
             "kba_numbers":r.kba_numbers} for r in rows]


@router.post("/vehicle-directory/import", tags=["Vehicle directory"])
async def directory_import(db: DB,who: Auth,file:UploadFile=File(...),dry_run:bool=True):
    from app.services.catalogue_import import require_admin
    from app.services.vehicle_directory import apply_payload,MAX_UPLOAD
    require_admin(db,who)
    raw=await file.read(MAX_UPLOAD+1)
    if len(raw)>MAX_UPLOAD:raise HTTPException(413,"Файл перевищує 16 МБ")
    return apply_payload(db,raw,file.filename or "carpot-vehicles.txt",who.workspace_account_id,dry_run)


def _new_vehicle_oem_enrichment(account_id: str, vehicle_id: str):
    """Run once after a successful staged create; never block the response."""
    import logging
    from app.db import engine
    from app.services.auto_oem import enrich_vehicle
    try:
        enrich_vehicle(engine(),account_id,vehicle_id)
    except Exception:
        logging.getLogger(__name__).warning(
            'New-vehicle OEM enrichment deferred vehicle=%s',vehicle_id,exc_info=True
        )


def _reject_duplicate_vin(db, account_id, vin):
    if not vin:
        return
    existing_id = db.scalar(select(Vehicle.id).where(
        Vehicle.account_id == account_id, func.upper(func.trim(Vehicle.vin)) == vin))
    if existing_id:
        raise HTTPException(409, detail={
            "message": "Автомобіль із цим VIN уже існує",
            "vehicle_id": existing_id,
        })


def intake_replay(db, account_id, request_key, request_sha):
    if not request_key:
        return None
    row = db.scalar(select(Vehicle).where(Vehicle.account_id == account_id,
                                         Vehicle.dismantling_v3["intake_request_key"].as_string() == request_key))
    if row and (row.dismantling_v3 or {}).get("intake_request_sha") != request_sha:
        raise HTTPException(409, "Цей запит уже створив автомобіль. Почніть нове додавання")
    return row


@router.post("/vehicles", status_code=201, tags=["Vehicles"])
def vehicle_create(data: VehicleInput, db: DB, who: Auth, background_tasks: BackgroundTasks):
    values = data.model_dump()
    from app.services.catalogue_format import digest

    accept_base = values.pop("accept_base_catalogue")
    request_key = values.pop("intake_request_key")
    graph_sha = values.pop("catalogue_graph_sha")
    request_sha = digest(data.model_dump(mode="json", exclude={"intake_request_key"})) if request_key else None
    if existing := intake_replay(db, who.workspace_account_id, request_key, request_sha):
        return vehicle_view(db, existing, who.workspace_account_id)
    resolution = data.vin_resolution
    values.pop("vin_resolution", None)
    intake_mode = values.pop("vin_intake_mode", None)
    explicit_catalogue = intake_mode == "catalogue" or intake_mode == "manual" and data.source_identity is not None
    _reject_duplicate_vin(db, who.workspace_account_id, values.get('vin'))
    # Catalogue selections are not Vehicle columns. Revalidate by ID and
    # snapshot; never trust source names or attributes supplied by the browser.
    selection = data.catalogue_selection
    oracle_selection = data.source_identity
    if selection is not None and oracle_selection is not None:
        raise HTTPException(422,"Оберіть одну джерельну модифікацію")
    values.pop("catalogue_selection", None)
    values.pop("source_identity", None)
    oracle_identity = None
    stage13_plan = None
    if intake_mode and (resolution or selection):
        raise HTTPException(422, "Оберіть один спосіб додавання автомобіля")
    if accept_base and (intake_mode != "manual" or oracle_selection or resolution):
        raise HTTPException(422, "Базовий каталог можна обрати при ручному додаванні")
    if request_key and intake_mode == "manual" and not (oracle_selection or accept_base):
        raise HTTPException(422, "Оберіть модифікацію або підтвердьте базовий каталог")
    if (explicit_catalogue and not oracle_selection) or (graph_sha and not explicit_catalogue):
        raise HTTPException(422, "Оберіть модифікацію з каталогу")
    intake_state = {"vin_intake": intake_mode} if intake_mode else {}
    if values["vin"] and (selection or oracle_selection and not explicit_catalogue):
        raise HTTPException(422, "Для VIN виберіть модифікацію за перевіреним контекстом")
    if resolution:
        from app.permissions import require_permission
        from app.services import vin_resolution
        from app.services.unified_catalogue import CatalogueAdapter
        if not values["vin"] or selection or oracle_selection or values.get("ktype"):
            raise HTTPException(422, "Некоректна комбінація джерел VIN")
        context = vin_resolution.trusted_context(resolution.context, who, values["vin"])
        evidence = vin_resolution.effective_evidence(context, resolution.clarifications)
        vin_resolution.validate_vehicle_fields(values, evidence)
        values["vin_details"] = vin_resolution.vehicle_details(context, evidence)
        if resolution.choice:
            require_permission(who, "vehicles.create", "catalog.view")
            adapter = CatalogueAdapter()
            candidate, _ = vin_resolution.selected_candidate(adapter, context, resolution.clarifications,
                                                                resolution.choice, who)
            # Keep the decoded observation in vin_details. The explicit
            # source selection resolves contradictory model names.
            if vin_resolution.policy.model_relation(values["model"], candidate["model"]) != "compatible":
                values["model"] = candidate["model"]
            can_prepare = "dismantling.manage" in who.permissions
            readiness, stage13_plan = vin_resolution.graph_preview(adapter, candidate) if can_prepare else ("identity_only", None)
            if resolution.graph_sha and (not stage13_plan
                    or stage13_plan["payload"]["source_snapshot_sha"] != resolution.graph_sha):
                raise HTTPException(409, "Версія графа запчастин змінилася. Перевірте вибір ще раз")
            oracle_identity = vin_resolution.source_identity(candidate, readiness,
                allow_upgrade=can_prepare and readiness != "unsupported")
        elif resolution.graph_sha:
            raise HTTPException(422, "Оберіть модифікацію перед перевіркою графа")
        if not stage13_plan and not resolution.accept_base_catalogue:
            raise HTTPException(422, "Підтвердьте модифікацію з каталогом запчастин або явно погодьте базовий каталог")
    if resolution:
        intake_state = {"vin_intake": "reviewed"}
    if oracle_selection is not None:
        from app.permissions import require_permission
        from app.services import vin_resolution, vin_source_directory
        from app.services.unified_catalogue import CatalogueAdapter

        require_permission(who,"vehicles.create","catalog.view")
        if explicit_catalogue:
            require_permission(who, "dismantling.manage")
            adapter = CatalogueAdapter()
            oracle_identity, attributes, fields = vin_source_directory.catalogue_identity(
                adapter, oracle_selection, manufacturer=values["manufacturer"], model=values["model"], year=values["year"])
            readiness, stage13_plan = vin_resolution.graph_preview(adapter, oracle_identity)
            if not stage13_plan:
                if readiness in ("unavailable", "unsupported", "identity_only"):
                    raise HTTPException(503, "Каталог запчастин тимчасово недоступний. Спробуйте ще раз або додайте автомобіль вручну")
                raise HTTPException(409, "Для обраної модифікації запчастин у каталозі не знайдено")
            if graph_sha and graph_sha != stage13_plan["payload"]["source_snapshot_sha"]:
                raise HTTPException(409, "Каталог змінився. Оновіть план розбору")
            oracle_identity.update(source_attributes=attributes, catalogue_readiness=readiness,
                                   allow_upgrade=True, directory_snapshot=digest(oracle_identity))
            for field, (value, label) in fields.items():
                if field in ("engine_code", "fuel_type", "drive_type", "transmission") and not values.get(field):
                    values[field] = value if field == "drive_type" else label
                elif field == "engine_displacement_l" and not values.get(field) and 0.05 <= value <= 99.9:
                    from decimal import Decimal
                    values[field] = Decimal(str(value)).quantize(Decimal("0.1"))
        else:
            oracle_identity = vin_source_directory.confirm_identity(
                oracle_selection, manufacturer=values["manufacturer"], model=values["model"])
    source_entry = source_plan = None
    if selection is not None:
        from app.permissions import require_permission
        from app.services.unified_catalogue import CatalogueAdapter
        from app.services.vin_catalogue_matching import validate_selection
        require_permission(who, "vehicles.create", "catalog.view", "dismantling.manage")
        source_entry, source_plan = validate_selection(
            CatalogueAdapter(), selection=selection,
            manufacturer=values["manufacturer"], model=values["model"],
            generation=values.get("generation") or "", year=values.get("year"),
        )
    if values["donor_id"] is None:
        values["donor_id"] = automatic_donor_id(db, who.workspace_account_id)
    # Serialize allocation even when callers supply their own donor_id.
    db.scalar(select(Account).where(Account.id == who.workspace_account_id).with_for_update())
    if existing := intake_replay(db, who.workspace_account_id, request_key, request_sha):
        return vehicle_view(db, existing, who.workspace_account_id)
    if request_key:
        intake_state.update(intake_request_key=request_key, intake_request_sha=request_sha)
    # Catalogue reads run before the lock. Another request can commit this VIN
    # in that interval, so the preflight check cannot authorize the insert.
    _reject_duplicate_vin(db, who.workspace_account_id, values.get('vin'))
    if values.get('vin_details') and not resolution:
        values['vin_details']={**values['vin_details'],'trust':'user_confirmed_reported_not_factory_verified'}
    number = (db.scalar(select(func.max(Vehicle.number)).where(Vehicle.account_id == who.workspace_account_id)) or 0) + 1
    row = Vehicle(account_id=who.workspace_account_id, number=number, **values)
    db.add(row)
    if intake_state:
        row.dismantling_v3 = intake_state
    if selection is not None:
        # One donor, one versioned source plan. Potential dismantling types are
        # NOT physical stock and require later explicit confirmation for receipt.
        from app.services import unified_catalogue as catalogue
        from app.services.dismantling_plan_v3 import generator_basis
        db.flush()
        payload = source_plan["payload"]
        row.dismantling_v3 = {**(row.dismantling_v3 or {}), "global_selection": dict(
            car_id=selection.source_modification_id,
            model_id=selection.model_id,
            manufacturer_id=selection.manufacturer_id,
            source_snapshot_sha=selection.source_snapshot_sha,
            modification_description=payload["modification"].get("description"),
            source_specifications=(source_entry.get("specifications") or [])[:100],
            vehicle_basis=catalogue.vehicle_basis(row),
            identity_fingerprint=generator_basis(row),
            confirmation="user_selected",
            vin_verified=False,
        )}
        catalogue.persist(db, row, source_plan, allow_partial=True)
    elif oracle_identity is not None:
        # Exact Oracle source identity is intentionally separate from the pinned
        # part graph. No synthetic Catalogue/OEM applicability is created.
        from app.services.dismantling_plan_v3 import generator_basis
        db.flush()
        row.dismantling_v3={**(row.dismantling_v3 or {}),
            "oracle_vehicle_identity":{**oracle_identity,
                "identity_fingerprint":generator_basis(row)}}
        if stage13_plan:
            vin_resolution.persist_graph(db, row, stage13_plan, readiness=oracle_identity["catalogue_readiness"])
    record(db, who.workspace_account_id, row, "vehicle_create", "Додано донора", {})
    if accept_base and "dismantling.manage" in who.permissions:
        from app.services import dismantling
        dismantling.start(db, row.id, who.workspace_account_id)
        row.dismantling_v3 = {**row.dismantling_v3, "unified_base": True}
    db.commit()
    # Staging-only OEM enrichment starts immediately AFTER the vehicle is committed.
    # The periodic, idempotent sweep remains the retry path after transient failures.
    from app.config import is_staging
    import os
    if (is_staging() and os.getenv('WAREHOUSE_CATALOGUE_URL')
            and os.getenv('WAREHOUSE_CATALOGUE_KEY')
            and os.getenv('WAREHOUSE_AUTO_OEM_ENABLED','true').lower()=='true'):
        background_tasks.add_task(_new_vehicle_oem_enrichment,who.workspace_account_id,row.id)
    return vehicle_view(db, row, who.workspace_account_id)



@router.get("/vehicles/vin/source-manufacturers", tags=["Vehicles"])
def vin_source_manufacturers(who: Auth, manufacturer: str=Query(min_length=2,max_length=40)):
    from app.permissions import require_permission
    from app.services.vin_source_directory import manufacturer_choices
    require_permission(who,"vehicles.view","catalog.view")
    return manufacturer_choices(manufacturer)


@router.get("/vehicles/vin/source-manufacturer-directory", tags=["Vehicles"])
def vin_manufacturer_directory(who: Auth, kind: Literal["passenger", "commercial"],
                               name: str = Query("", max_length=100), after: int = Query(0, ge=0)):
    from app.permissions import require_permission
    from app.services.unified_catalogue import CatalogueAdapter
    from app.services.vin_source_directory import manufacturer_page

    require_permission(who, "vehicles.view", "catalog.view")
    return manufacturer_page(CatalogueAdapter(), kind=kind, name=name, after=after)


@router.get("/vehicles/vin/source-graph", tags=["Vehicles"])
def vin_source_graph(who: Auth, kind: Literal["passenger", "commercial"],
                     manufacturer_id: int = Query(gt=0), model_id: int = Query(gt=0),
                     modification_id: int = Query(gt=0), manufacturer: str = Query(min_length=1, max_length=128),
                     model: str = Query(min_length=1, max_length=128), year: int | None = Query(None, ge=1886, le=2100)):
    from app.permissions import require_permission
    from app.services import vin_resolution, vin_source_directory
    from app.services.unified_catalogue import CatalogueAdapter

    require_permission(who, "vehicles.view", "catalog.view", "dismantling.manage")
    adapter = CatalogueAdapter()
    selection = VinSourceIdentity(confirmed=True, kind=kind, manufacturer_id=manufacturer_id, model_id=model_id,
                                  source_modification_id=modification_id)
    identity, attributes, fields = vin_source_directory.catalogue_identity(
        adapter, selection, manufacturer=manufacturer, model=model, year=year)
    readiness, plan = vin_resolution.graph_preview(adapter, identity)
    return {**vin_resolution.graph_status(readiness, plan), "modification": identity["modification"],
            "attributes": attributes, "characteristics": {field: label for field, (_, label) in fields.items()}}


@router.get("/vehicles/vin/source-models", tags=["Vehicles"])
def vin_source_models(who: Auth, manufacturer_id: int=Query(gt=0),
                      kind: Literal["passenger","commercial"]=Query(),
                      after: int=Query(default=0,ge=0)):
    from app.permissions import require_permission
    from app.services.vin_source_directory import source_page
    require_permission(who,"vehicles.view","catalog.view")
    return source_page("models",source_id=manufacturer_id,kind=kind,after=after)


@router.get("/vehicles/vin/source-modifications", tags=["Vehicles"])
def vin_source_modifications(who: Auth, model_id: int=Query(gt=0),
                             kind: Literal["passenger","commercial"]=Query(),
                             after: int=Query(default=0,ge=0)):
    from app.permissions import require_permission
    from app.services.vin_source_directory import source_page
    require_permission(who,"vehicles.view","catalog.view")
    return source_page("modifications",source_id=model_id,kind=kind,after=after)


@router.get("/vehicles/vin/catalogue-candidates", tags=["Vehicles"])
def vin_catalogue_candidates(
    db: DB, who: Auth,
    manufacturer: str = Query(min_length=2, max_length=100),
    model: str = Query(default="", max_length=100),
    after: int = Query(default=0, ge=0),
):
    """Read-only candidates for all makes. Never infer vehicle fitment from a model name."""
    from app.permissions import require_permission
    from app.services.unified_catalogue import CatalogueAdapter
    from app.services.vin_catalogue_matching import search_candidates
    require_permission(who, "vehicles.view", "catalog.view")
    return search_candidates(CatalogueAdapter(), manufacturer=manufacturer, model=model, after=after)


@router.get("/vehicles/vin/decode", tags=["Vehicles"])
def vehicle_vin_decode(who: Auth, response: Response, vin: str = Query(min_length=17, max_length=17)):
    """Authenticated, read-only VIN lookup. Uncertain fields require user confirmation."""
    import re
    value=vin.strip().upper()
    if not re.fullmatch('[A-HJ-NPR-Z0-9]{17}',value):
        raise HTTPException(422,'VIN має складатися з 17 символів без I, O, Q')
    from app.services.vin_lookup import lookup
    from app.services.vin_resolution import issue_context
    decoded = lookup(value, public_only=True)
    response.headers["Cache-Control"] = "no-store"
    return {**decoded, "resolution_context": issue_context(decoded, who)}


def vin_clarifications(header):
    from urllib.parse import unquote
    from pydantic import ValidationError
    try:
        return VinClarifications.model_validate_json(unquote(header))
    except ValidationError:
        raise HTTPException(422, "Некоректні уточнення VIN") from None


@router.get("/vehicles/vin/resolution", tags=["Vehicles"])
def vehicle_vin_resolution(
    who: Auth, response: Response,
    context: Annotated[str, Header(alias="X-Vin-Context", max_length=12000)],
    clarification: Annotated[str, Header(alias="X-Vin-Clarifications", max_length=9000)] = "{}",
    maker: str | None = Query(None, pattern=r"^(passenger|commercial):[1-9][0-9]{0,10}$"),
    model_id: int | None = Query(None, gt=0),
    after: int = Query(0, ge=0),
    model_after: int = Query(0, ge=0),
):
    from app.services import vin_resolution
    from app.services.unified_catalogue import CatalogueAdapter

    if ((model_id or model_after) and not maker) or (after and not model_id) or (model_after and model_id):
        raise HTTPException(422, "Укажіть виробника й модель для продовження пошуку")
    response.headers["Cache-Control"] = "no-store"
    trusted = vin_resolution.trusted_context(context, who)
    return vin_resolution.search(CatalogueAdapter(), trusted, vin_clarifications(clarification), who,
                                 selected_maker=maker, selected_model=model_id, after=after, model_after=model_after)


@router.get("/vehicles/vin/resolution-graph", tags=["Vehicles"])
def vehicle_vin_resolution_graph(
    who: Auth, response: Response,
    context: Annotated[str, Header(alias="X-Vin-Context", max_length=12000)],
    choice: Annotated[str, Header(alias="X-Vin-Choice", max_length=1800)],
    clarification: Annotated[str, Header(alias="X-Vin-Clarifications", max_length=9000)] = "{}",
):
    from app.services import vin_resolution
    from app.services.unified_catalogue import CatalogueAdapter

    response.headers["Cache-Control"] = "no-store"
    adapter = CatalogueAdapter()
    trusted = vin_resolution.trusted_context(context, who)
    if "dismantling.manage" not in who.permissions:
        return {"status": "identity_only", "source_snapshot_sha": None}
    candidate, _ = vin_resolution.selected_candidate(adapter, trusted, vin_clarifications(clarification), choice, who)
    readiness, plan = vin_resolution.graph_preview(adapter, candidate)
    return vin_resolution.graph_status(readiness, plan)


@router.get("/vehicles/{id}", tags=["Vehicles"])
def vehicle_get(id: str, db: DB, who: Auth):
    return vehicle_view(db, owned(db, Vehicle, id, who.workspace_account_id), who.workspace_account_id)


@router.delete("/vehicles/{id}", status_code=204, tags=["Vehicles"])
def delete_vehicle(id: str, db: DB, who: Auth):
    from app.services.vehicle_delete import purge

    if not vehicle_delete_enabled():
        raise HTTPException(404, "Запис не знайдено")
    purge(db, id, who.workspace_account_id, who.actor_id)
    return Response(status_code=204)


@router.put("/vehicles/{id}", tags=["Vehicles"])
def vehicle_update(id: str, data: VehicleInput, db: DB, who: Auth):
    db.scalar(select(Account).where(Account.id==who.workspace_account_id).with_for_update())
    row = owned(db, Vehicle, id, who.workspace_account_id, lock=True, active=True)
    before = snapshot(row)
    changes = data.model_dump(exclude_unset=True)
    resolution = changes.pop("vin_resolution", None)
    intake_mode = changes.pop("vin_intake_mode", None)
    if changes.pop("accept_base_catalogue", None) or changes.pop("intake_request_key", None) or changes.pop("catalogue_graph_sha", None):
        raise HTTPException(422, "Ці поля застосовуються лише під час додавання")
    if resolution is not None or intake_mode is not None or changes.pop("catalogue_selection", None) is not None or changes.pop("source_identity", None) is not None:
        raise HTTPException(422, "Для наявного автомобіля використайте підтверджений вибір модифікації у картці")
    if ((row.dismantling_v3 or {}).get("vin_intake") == "reviewed"
            and ("vin_details" in changes or "vin" in changes and changes["vin"] != row.vin)):
        raise HTTPException(409, "VIN і звіт декодування збережено разом із підтвердженим контекстом")
    if changes.get('vin'):
        existing=db.scalar(select(Vehicle).where(Vehicle.account_id==who.workspace_account_id,func.upper(func.trim(Vehicle.vin))==changes['vin'],Vehicle.id!=id))
        if existing:raise HTTPException(409,detail={'message':'Автомобіль із цим VIN уже існує','vehicle_id':existing.id})
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
    subcategory_id: str | None = Query(None,max_length=80),
    category_facets: bool = False,
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
    category_filters = []
    # Compatible with legacy single category_id; grouped catalogue tiles send
    # a comma-separated collection of legacy IDs. No changes to stock FKs.
    if category_id == '__review__':
        from app.services.plan_parts_classification import CATEGORY_ALIASES, normalize
        aliases={normalize(n) for title,names in CATEGORY_ALIASES.items() for n in (title,*names)}
        roots=[c.id for c in db.scalars(select(Category).where(Category.account_id==who.workspace_account_id,Category.archived.is_(False),Category.kind=='category',Category.parent_id.is_(None))) if normalize(c.name) in aliases]
        category_filters.append(or_(Part.category_id.is_(None),Part.category_id.not_in(roots)))
    elif category_id is not None:
        category_ids = list(dict.fromkeys(v.strip() for v in category_id.split(",") if v.strip()))
        if not category_ids or len(category_ids) > 50 or any(len(v) > 80 for v in category_ids):
            raise HTTPException(422, "Invalid category_id selection")
        category_filters.append(Part.category_id.in_(category_ids))
    if subcategory_id is not None:
        category_filters.append(Part.subcategory_id.is_(None) if subcategory_id=="__none__" else Part.subcategory_id==subcategory_id)
    for col, value in [
        (Part.vehicle_id, vehicle_id),
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
        category_filters=category_filters,
        category_facets=category_facets,
        currency_aware=request.headers.get("X-Warehouse-Client")=="5",
    )


@router.post("/parts", status_code=201, tags=["Inventory"])
def part_create(data: PartInput, db: DB, who: Auth):
    if data.individually_tracked and not data.serial_number:raise HTTPException(422,"Для індивідуального обліку потрібен серійний номер")
    validate_part_links(db, data, who.workspace_account_id)
    row = Part(account_id=who.workspace_account_id, **data.model_dump())
    db.add(row)
    record(db, who.workspace_account_id, row, "part_create", "Додано позицію без залишку", {})
    db.commit()
    return {**snapshot(row), "available_quantity": row.available_quantity}


def _part_stock_received_at(db, account_id, part_id):
    """Actual first receipt timestamp, not the card creation timestamp."""
    return db.scalar(
        select(Operation.created_at)
        .where(Operation.account_id == account_id,
               Operation.part_id == part_id,
               Operation.type == "receipt")
        .order_by(Operation.created_at.asc())
        .limit(1)
    )

@router.get("/parts/{id}", tags=["Inventory"])
def part_get(id: str, request: Request, db: DB, who: Auth):
    row = owned(db, Part, id, who.workspace_account_id)
    result={**snapshot(row), "available_quantity": row.available_quantity}
    result["stock_received_at"] = _part_stock_received_at(
        db, who.workspace_account_id, row.id
    )
    # Previous UI labels every price UAH. Do not expose USD as a misleading
    # hryvnia amount to that client; the exact stored value is never changed.
    if row.currency!='UAH' and request.headers.get('X-Warehouse-Client')!='5':
        result.update(selling_price=None,price_requires_currency_client=True)
    from app.services.assemblies import part_context
    context=part_context(db,who.workspace_account_id,row.id)
    if context:
        if 'orders.view' not in who.permissions:context.pop('order_id',None);context.pop('order_number',None)
        result['assembly_context']=context
    return result


@router.put("/parts/{id}", tags=["Inventory"])
def part_update(id: str, data: PartInput, db: DB, who: Auth):
    row = owned(db, Part, id, who.workspace_account_id, lock=True, active=True)
    validate_part_links(db, data, who.workspace_account_id)
    from app.services.assemblies import protect_identity,managed_part
    managed=managed_part(db,row)
    if data.individually_tracked and not data.serial_number and not managed:raise HTTPException(422,"Для індивідуального обліку потрібен серійний номер")
    if managed and row.individually_tracked and 'individually_tracked' in data.model_fields_set and not data.individually_tracked:
        raise HTTPException(409,'Індивідуальний фізичний ID компонента не можна перетворити на кількісну позицію')
    protect_identity(db,row,data.vehicle_id)
    if data.individually_tracked and row.quantity > 1:
        raise HTTPException(
            409, "Спочатку розділіть кількісну позицію на окремі одиниці"
        )
    before = snapshot(row)
    changes=data.model_dump()
    if managed:
        for field in ('individually_tracked','serial_number'):
            if field not in data.model_fields_set:changes.pop(field,None)
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
    # Older forms must not erase a subsequently assigned reference by omission.
    for field in ('article_number','oem_number'):
        if field not in data.model_fields_set:changes.pop(field,None)
    for k, v in changes.items():
        setattr(row, k, v)
    if row.article_number!=before['article_number']:
        row.article_brand=''  # A manually changed number cannot retain a supplier's brand/provenance.
        row.article_provenance=dict(source='manual',confirmed_by=who.actor_id,confirmed_at=datetime.now(timezone.utc).isoformat(),status='user_confirmed' if row.article_number else 'cleared')
    if row.oem_number!=before['oem_number']:
        row.oem_provenance=dict(source='manual',confirmed_by=who.actor_id,confirmed_at=datetime.now(timezone.utc).isoformat(),status='user_confirmed' if row.oem_number else 'cleared')
    record(db, who.workspace_account_id, row, "part_update", "Оновлено картку запчастини", before)
    db.commit()
    return {**snapshot(row), "available_quantity": row.available_quantity,
            "stock_received_at": _part_stock_received_at(db, who.workspace_account_id, row.id)}


@router.patch('/parts/{id}/characteristics', tags=['Inventory'])
def part_characteristics(id: str, data: PartCharacteristicsInput, db: DB, who: Auth):
    row=owned(db,Part,id,who.workspace_account_id,lock=True,active=True)
    before=snapshot(row)
    from app.services.auto_oem import physical_oem_confirmed

    needs_confirmation = data.confirm_physical_oem and not physical_oem_confirmed(row)
    if not needs_confirmation and all(getattr(row,k)==v for k,v in data.values.items()):
        return {**before,'available_quantity':row.available_quantity,
                'stock_received_at':_part_stock_received_at(db,who.workspace_account_id,row.id)}
    if any(getattr(row,k)!=v for k,v in data.expected.items()):
        raise HTTPException(409,'Характеристики вже змінено. Перечитайте картку та порівняйте значення.')
    for key,value in data.values.items():setattr(row,key,value)
    if 'oem_number' in data.values:
        previous=before.get('oem_provenance') or {}
        option=next((a for a in previous.get('alternatives',[]) if a.get('oem_number')==row.oem_number),None)
        if data.confirm_physical_oem or not option:
            row.oem_provenance = dict(source='manual', confirmed_by=who.actor_id,
                confirmed_at=datetime.now(timezone.utc).isoformat(),
                status='user_confirmed' if row.oem_number else 'cleared')
            if data.confirm_physical_oem:
                row.oem_provenance['physical_number_confirmed_by_user'] = True
        else:
            row.oem_provenance = {**previous, **option, 'status': 'user_selected_cross_reference'}
    record(db,who.workspace_account_id,row,'part_update','Оновлено OEM / колір деталі',before)
    db.commit()
    return {**snapshot(row),'available_quantity':row.available_quantity,
            'stock_received_at':_part_stock_received_at(db,who.workspace_account_id,row.id)}


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
    if data.assembly_token is None:payload.pop('assembly_token',None)
    if not data.assembly_description:payload.pop('assembly_description',None)
    if not data.assembly_remainder:payload.pop('assembly_remainder',None)
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
