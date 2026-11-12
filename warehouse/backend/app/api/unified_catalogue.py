"""Authenticated Catalogue bridge. No paid provider requests in these endpoints."""
from typing import Annotated
from pydantic import Field
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.api.secure_route import SecureRoute
from app.api.deps import identity, Identity
from app.db import get_db
from app.models import Vehicle
from app.permissions import require_permission
from app.schemas import Input
from app.services.inventory import owned
from app.services import unified_catalogue as service

router = APIRouter(route_class=SecureRoute, prefix='/api/v1/vehicles')
DB = Annotated[Session, Depends(get_db)]
Auth = Annotated[Identity, Depends(identity)]


@router.get('/{id}/unified-catalogue')
def status(id: str, db: DB, who: Auth, model_id: int | None = Query(None, gt=0)):
    require_permission(who, 'vehicles.view', 'catalog.view')
    v = owned(db, Vehicle, id, who.workspace_account_id)
    saved = service.saved_state(v)
    if (v.dismantling_v3 or {}).get('unified_base'):
        from sqlalchemy import select, func
        from app.models import DismantlingItem
        count=db.scalar(select(func.count()).select_from(DismantlingItem).where(DismantlingItem.vehicle_id==v.id,DismantlingItem.account_id==who.workspace_account_id))
        return dict(saved=True,source='base',type_count=count)
    if saved:
        return dict(saved=True, source='catalogue', review_required=service.needs_review(v), modification=saved['payload']['modification'],
            source_modification_id=saved['payload']['car_id'], model_id=saved['payload']['model_id'],
            observed_at=saved['payload']['observed_at'], type_count=len(saved['payload']['categories']))
    if model_id is None or v.manufacturer.strip().casefold() != 'volvo':
        return dict(saved=False, items=[], available=False)
    try:
        return dict(saved=False, available=True, **service.CatalogueAdapter().modifications(model_id))
    except service.CatalogueUnavailable:
        return dict(saved=False, available=False, items=[], message='Власний каталог зараз недоступний. Збережений Plan.Parts залишається доступним.')


class Selection(Input):
    model_id: int = Field(strict=True, gt=0)
    source_modification_id: int = Field(strict=True, gt=0)
    confirm_exact_modification: bool = False


@router.post('/{id}/unified-catalogue')
def create(id: str, data: Selection, db: DB, who: Auth):
    require_permission(who, 'vehicles.view', 'dismantling.manage')
    v = owned(db, Vehicle, id, who.workspace_account_id, lock=True, active=True)
    if not data.confirm_exact_modification or min(data.model_id, data.source_modification_id) <= 0:
        raise HTTPException(422, 'Підтвердіть конкретну модифікацію Catalogue')
    if v.manufacturer.strip().casefold() != 'volvo':
        raise HTTPException(409, 'Цей каталог підтримує тільки Volvo')
    import re
    expected = {13084:'XC90',37773:'XC60'}.get(data.model_id)
    if not expected or not re.search(r'\b'+expected+r'\b',v.model,re.IGNORECASE):
        raise HTTPException(409,'Модель Catalogue не відповідає моделі автомобіля')
    saved = service.saved_state(v)
    if saved:
        if service.needs_review(v):raise HTTPException(409,'Автомобіль змінився; збережений план потребує звірки, дані не видалено')
        if saved['payload']['car_id'] != data.source_modification_id or saved['payload']['model_id'] != data.model_id:
            raise HTTPException(409, 'Наявний план збережено; автоматична заміна модифікації заборонена')
        return dict(saved=True, source='catalogue', created=0)
    from app.services.checklists import stored_categories
    saved_pp = bool(v.ktype and (stored_categories(db, v.id, who.workspace_account_id, v.ktype) or (v.checklist_ktype == v.ktype and v.checklist_synced_at)))
    result = service.CatalogueResolver().resolve(make=v.manufacturer, source_modification_id=data.source_modification_id, saved_plan_parts=saved_pp)
    if result['source'] == 'catalogue':
        if result['plan']['payload']['model_id'] != data.model_id:
            raise HTTPException(409, 'Модифікація належить іншій моделі')
        service.persist(db, who, v, result['plan'])
        db.commit()
        return dict(saved=True, source='catalogue', created=len(result['plan']['payload']['categories']))
    return dict(saved=False, **result)


def selected_row(db, who, v, key, *, write=False):
    from sqlalchemy import select
    from app.models import DismantlingItem
    state = service.saved_state(v)
    if write and service.needs_review(v):raise HTTPException(409,'Модифікація автомобіля змінилася. План збережено; перед складськими діями потрібна звірка.')
    if (v.dismantling_v3 or {}).get('unified_base') and key.startswith('base:'):
        row=db.scalar(select(DismantlingItem).where(DismantlingItem.id==key.removeprefix('base:'),DismantlingItem.account_id==who.workspace_account_id,DismantlingItem.vehicle_id==v.id).with_for_update())
        if row is None: raise HTTPException(404,'Позицію плану не знайдено')
        return row,None,None
    if not state or not key.startswith('catalogue:'):
        raise HTTPException(404, 'Позицію плану не знайдено')
    row = db.scalar(select(DismantlingItem).where(DismantlingItem.id == key.removeprefix('catalogue:'),
        DismantlingItem.account_id == who.workspace_account_id, DismantlingItem.vehicle_id == v.id,
        DismantlingItem.source == 'carpot.catalogue.v1').with_for_update())
    prefix = f"car:{state['payload']['car_id']}:product:"
    if row is None or not row.catalog_key.startswith(prefix):
        raise HTTPException(404, 'Позицію плану не знайдено')
    product = next((r for r in state['payload']['categories'] if str(r['product_id']) == row.catalog_key[len(prefix):]), None)
    if product is None:
        raise HTTPException(404, 'Тип каталогу не знайдено')
    return row, product, state


def source_value(row,key):
    return next((v for k,v in row.items() if k.casefold()==key.casefold()),None)


def saved_articles(product, state, *, oem_manufacturer_id=None):
    payload=state['payload']
    if payload.get('schema') in ('carpot.volvo.plan.v2','carpot.vehicle.plan.v1'):
        try:
            items=service.CatalogueAdapter().articles(payload['car_id'],product['product_id'],payload['source_snapshot_sha'],**({'global_source':True} if payload.get('schema')=='carpot.vehicle.plan.v1' else {}))
        except service.CatalogueUnavailable:
            raise HTTPException(503,'Артикули збереженої версії тимчасово недоступні. Платний запит не виконувався.') from None
        if len(items)!=product['article_count']:
            raise HTTPException(503,'Неповна відповідь збереженої версії каталогу')
    else:
        # Read compatibility only: previously saved raw snapshots are not rewritten.
        items=[payload['articles'][key] for key in product['articles']]
    result=[]
    for i,item in enumerate(items):
        supplier=item.get('supplier',[])
        article=item.get('article',[])
        result.append(dict(art_id=i+1,article_nr=item['article_number'],
            brand=str(source_value(supplier[0],'description') or '') if supplier else '',
            supplier_id=item['supplier_id'],part_name=str(source_value(article[0],'NormalizedDescription') or '') if article else '',
            characteristics={},source_attributes=item.get('attributes',[]),cross_references=item.get('crosses',[]),
            image_metadata=item.get('images',[]),photo=None,
            oem_numbers=sorted({str(source_value(r,'OENbr')) for r in item.get('oem',[]) if source_value(r,'OENbr') and (oem_manufacturer_id is None or source_value(r,'manufacturerId') == oem_manufacturer_id)}),
            observed_at=payload['observed_at'],fitment='source_modification_link',vin_verified=False))
    return result


@router.get('/{id}/unified-catalogue/articles')
def articles(id: str, db: DB, who: Auth, key: str = Query(max_length=100)):
    require_permission(who, 'vehicles.view', 'catalog.view')
    v = owned(db, Vehicle, id, who.workspace_account_id)
    _, product, state = selected_row(db, who, v, key)
    if state is None:raise HTTPException(409,'Стандартний план не має автоматичного підбору артикулів')
    return dict(articles=saved_articles(product, state), source='saved_catalogue', cost='free')


class StockSelection(Input):
    keys: list[str]
    confirm_physical_receipt: bool = False


@router.post('/{id}/unified-catalogue/stock')
def add_stock(id: str, data: StockSelection, db: DB, who: Auth):
    require_permission(who, 'vehicles.view', 'dismantling.manage', 'inventory.create', 'inventory.adjust_quantity')
    if not data.confirm_physical_receipt or not 1 <= len(data.keys) <= 100 or len(set(data.keys)) != len(data.keys):
        raise HTTPException(422, 'Підтвердіть надходження по 1 фізичній деталі; до 100 позицій')
    v = owned(db, Vehicle, id, who.workspace_account_id, lock=True, active=True)
    from app.services.dismantling import actions
    from app.api.dismantling import DismantlingAction
    from app.services import dismantling_workspace
    states = {r['key']: r['state'] for r in dismantling_workspace.read(db, who, v, 'base' if (v.dismantling_v3 or {}).get('unified_base') else 'catalogue')['items']}
    selected = [selected_row(db,who,v,key,write=True) for key in sorted(data.keys)]
    if any(product is not None and product.get('kind')!='part' for _,product,_ in selected):
        raise HTTPException(409,'Витратні матеріали, обладнання та неперевірені типи потребують окремої перевірки перед складським обліком')
    rows=[row for row,_,_ in selected]
    if any(states.get(key) in ('hidden', 'sold', 'empty') for key in data.keys):
        raise HTTPException(409, 'Приховані або продані позиції не оприбутковуються повторно')
    pending = [r.id for r in rows if r.received_at is None]
    if pending:
        actions(db, id, who.workspace_account_id, DismantlingAction(ids=pending, action='dismantled'))
        result = actions(db, id, who.workspace_account_id, DismantlingAction(ids=pending, action='receipt', quantity=1))
    else:
        result = {'updated': 0}
    db.commit()
    return dict(added=result['updated'], skipped=len(rows)-result['updated'])


class ArticleSelection(Input):
    key: str
    art_id: int
    part_id: str
    expected_article_number: str = ''
    expected_article_brand: str = ''


@router.post('/{id}/unified-catalogue/article')
def assign_article(id: str, data: ArticleSelection, db: DB, who: Auth):
    require_permission(who, 'vehicles.view', 'dismantling.manage', 'inventory.edit')
    v = owned(db, Vehicle, id, who.workspace_account_id, lock=True, active=True)
    row, product, state = selected_row(db, who, v, data.key, write=True)
    if state is None:raise HTTPException(409,'Стандартний план не має артикулів Catalogue')
    if row.part_id != data.part_id:
        raise HTTPException(409, 'Виберіть складську картку саме цієї позиції')
    from app.models import Part
    p = owned(db, Part, data.part_id, who.workspace_account_id, lock=True, active=True)
    if p.vehicle_id != v.id or (p.article_number or '', p.article_brand or '') != (data.expected_article_number, data.expected_article_brand):
        raise HTTPException(409, 'Картка змінилася. Оновіть дані перед призначенням')
    if p.article_provenance and p.article_provenance.get('source') == 'manual':
        raise HTTPException(409, 'Ручний артикул збережено. Змінюйте його в картці вручну.')
    offer = next((r for r in saved_articles(product, state) if r['art_id'] == data.art_id), None)
    if not offer or not offer['brand']:
        raise HTTPException(422, 'Перевірений виробник артикула відсутній')
    from app.services.inventory import record, snapshot
    before = snapshot(p)
    p.article_number, p.article_brand = offer['article_nr'], offer['brand']
    p.article_provenance = dict(source='carpot.catalogue', source_modification_id=state['payload']['car_id'],
        supplier_id=offer['supplier_id'], observed_at=offer['observed_at'], snapshot_sha=state['payload'].get('source_snapshot_sha',state['sha256']),
        verification='source_modification_link', vin_verified=False)
    record(db, who.workspace_account_id, p, 'part_update', 'Явно призначено артикул Catalogue; OEM і залишки не змінено', before)
    db.commit()
    return dict(saved=True)


@router.post('/{id}/unified-catalogue/base')
def create_base(id: str, db: DB, who: Auth):
    require_permission(who,'vehicles.view','dismantling.manage')
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    if (v.dismantling_v3 or {}).get('unified_base'):return dict(saved=True,source='base')
    from sqlalchemy import select
    from app.models import Part,DismantlingItem,VehicleChecklistItem
    if v.dismantling_v3 or any(db.scalar(select(cls.id).where(cls.account_id==who.workspace_account_id,cls.vehicle_id==v.id).limit(1)) for cls in (Part,DismantlingItem,VehicleChecklistItem)):
        raise HTTPException(409,'Автомобіль вже має збережені дані. Наявний план не замінено.')
    from app.services import dismantling
    result=dismantling.start(db,v.id,who.workspace_account_id)
    v.dismantling_v3={**(v.dismantling_v3 or {}),'unified_base':True}
    db.commit()
    return dict(saved=True,source='base',**result)


@router.get('/{id}/unified-catalogue/enrichment')
def article_enrichment(id: str, db: DB, who: Auth, part_id: str, supplier_id: int = Query(gt=0, le=65535)):
    """Any plan source can request exact existing article enrichment, read-only."""
    require_permission(who,'vehicles.view','catalog.view','inventory.view')
    v=owned(db,Vehicle,id,who.workspace_account_id)
    from app.models import Part
    p=owned(db,Part,part_id,who.workspace_account_id)
    if p.vehicle_id!=v.id:raise HTTPException(404,'Складську позицію не знайдено')
    if not p.article_number or not p.article_brand:
        return dict(available=False,reason='missing_exact_article_and_manufacturer')
    try:
        result=service.CatalogueAdapter().article(supplier_id,p.article_number,p.article_brand)
    except service.CatalogueUnavailable:
        return dict(available=False,reason='unverified_or_unavailable')
    return dict(available=True,**result)


class OemSelection(ArticleSelection):
    oem_number: str = Field(min_length=1,max_length=150)
    confirm_cross_reference: bool = False


@router.post('/{id}/unified-catalogue/oem')
def assign_oem(id: str, data: OemSelection, db: DB, who: Auth):
    require_permission(who,'vehicles.view','dismantling.manage','inventory.edit')
    if not data.confirm_cross_reference:raise HTTPException(422,'Підтвердіть вибір OEM-кроса; це не перевірка VIN')
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    row,product,state=selected_row(db,who,v,data.key,write=True)
    if state is None or row.part_id!=data.part_id:raise HTTPException(404,'Складську позицію каталогу не знайдено')
    from app.models import Part
    p=owned(db,Part,data.part_id,who.workspace_account_id,lock=True,active=True)
    if p.vehicle_id!=v.id:raise HTTPException(404,'Складську позицію не знайдено')
    offer=next((r for r in saved_articles(product,state) if r['art_id']==data.art_id),None)
    if not offer or data.oem_number not in offer['oem_numbers']:raise HTTPException(422,'OEM відсутній у збереженій відповіді')
    if p.oem_number:raise HTTPException(409,'Наявний OEM збережено; змініть його вручну в картці')
    from app.services.inventory import record,snapshot
    before=snapshot(p)
    p.oem_number=data.oem_number
    p.oem_provenance=dict(source='carpot.catalogue',status='user_selected_cross_reference',
        source_modification_id=state['payload']['car_id'],supplier_id=offer['supplier_id'],
        source_article=offer['article_nr'],observed_at=offer['observed_at'],snapshot_sha=state['payload'].get('source_snapshot_sha',state['sha256']),
        confirmed_by=who.actor_id,vin_verified=False)
    record(db,who.workspace_account_id,p,'part_update','Явно призначено OEM-крос без твердження VIN-сумісності',before)
    db.commit()
    return dict(saved=True)


@router.get('/catalogue-directory/available')
def global_directory(db: DB, who: Auth, after: int = Query(0, ge=0)):
    require_permission(who, 'vehicles.view', 'catalog.view')
    try:
        return service.CatalogueAdapter().directory(after)
    except service.CatalogueUnavailable:
        raise HTTPException(503, 'Глобальний каталог недоступний') from None


class GlobalVehicle(Input):
    request_key: str = Field(min_length=36,max_length=36)
    source_modification_id: int = Field(strict=True,gt=0)
    year: int = Field(ge=1886, le=2100)


@router.post('/catalogue-directory/vehicles', status_code=201)
def global_vehicle(data: GlobalVehicle, db: DB, who: Auth):
    require_permission(who, 'vehicles.create', 'catalog.view')
    from sqlalchemy import select,func
    from app.models import Account
    from app.api.routes import vehicle_view
    from app.services.vehicle_catalog import automatic_donor_id
    from app.services.inventory import record
    # Workspace lock serializes both donor numbering and retry-key lookup.
    db.scalar(select(Account).where(Account.id==who.workspace_account_id).with_for_update())
    for existing in db.scalars(select(Vehicle).where(Vehicle.account_id==who.workspace_account_id)):
        if (existing.dismantling_v3 or {}).get('global_selection',{}).get('request_key')==data.request_key:
            selection=existing.dismantling_v3['global_selection']
            if selection['car_id']!=data.source_modification_id or existing.year!=data.year:
                raise HTTPException(409,'Ключ повторного запиту вже використано')
            return vehicle_view(db,existing,who.workspace_account_id)
    try:
        plan=service.CatalogueAdapter().plan(data.source_modification_id,global_source=True)
        directory=service.CatalogueAdapter().directory(car_id=data.source_modification_id)['items']
        entry=next((r for r in directory if r['source_modification_id']==data.source_modification_id),None)
    except service.CatalogueUnavailable:
        raise HTTPException(503, 'Не вдалося перевірити каталог') from None
    if not entry or entry.get('snapshot_sha')!=plan['payload']['source_snapshot_sha'] or entry['model_id']!=plan['payload']['model_id'] or entry['manufacturer_id']!=plan['payload']['manufacturer_id'] or not plan['payload']['categories']:
        raise HTTPException(409,'Підтверджених каталожних зв’язків немає')
    number=(db.scalar(select(func.max(Vehicle.number)).where(Vehicle.account_id==who.workspace_account_id)) or 0)+1
    vehicle=Vehicle(account_id=who.workspace_account_id,number=number,donor_id=automatic_donor_id(db,who.workspace_account_id),
        manufacturer=entry['manufacturer'],model=entry['model'],generation=entry.get('generation') or '',year=data.year,
        engine='',status='dismantling',
        dismantling_v3={'global_selection':dict(car_id=data.source_modification_id,model_id=entry['model_id'],
            manufacturer_id=entry['manufacturer_id'],modification_description=plan['payload']['modification'].get('description'),
            source_specifications=entry.get('specifications',[])[:100],request_key=data.request_key,source_snapshot_sha=plan['payload']['source_snapshot_sha'])})
    db.add(vehicle);db.flush()
    vehicle.dismantling_v3={'global_selection':{**vehicle.dismantling_v3['global_selection'],'vehicle_basis':service.vehicle_basis(vehicle)}}
    record(db,who.workspace_account_id,vehicle,'vehicle_create','Додано автомобіль із глобального каталогу',{})
    db.commit()
    return vehicle_view(db,vehicle,who.workspace_account_id)


@router.post('/{id}/global-dismantling')
def global_dismantling(id: str, db: DB, who: Auth):
    require_permission(who, 'vehicles.view', 'dismantling.manage')
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    saved=service.saved_state(v)
    selection=(v.dismantling_v3 or {}).get('global_selection')
    if not selection:
        raise HTTPException(409,'Для цього автомобіля не вибрано глобальну модифікацію. Наявні дані збережено.')
    if service.needs_review(v) or (selection.get('vehicle_basis') and selection['vehicle_basis']!=service.vehicle_basis(v)):
        raise HTTPException(409,'Характеристики автомобіля змінились. Збережені дані залишено; потрібна звірка модифікації.')
    if saved:
        return dict(saved=True,created=0)
    try:
        envelope=service.CatalogueAdapter().plan(selection['car_id'],global_source=True)
    except service.CatalogueUnavailable:
        raise HTTPException(503,'Не вдалося отримати глобальний каталог') from None
    if envelope['payload']['model_id']!=selection['model_id'] or envelope['payload']['source_snapshot_sha']!=selection['source_snapshot_sha']:
        raise HTTPException(409,'Версія каталогу змінилась; потрібне повторне підтвердження модифікації')
    service.persist(db,who,v,envelope,allow_partial=True)
    db.commit()
    return dict(saved=True,created=len(envelope['payload']['categories']))


@router.get('/{id}/global-dismantling')
def global_saved(id: str, db: DB, who: Auth):
    require_permission(who,'vehicles.view','catalog.view')
    v=owned(db,Vehicle,id,who.workspace_account_id)
    state=service.saved_state(v)
    from sqlalchemy import select
    from app.models import DismantlingItem
    keys={int(r.catalog_key.rsplit(':',1)[1]):'catalogue:'+r.id for r in db.scalars(select(DismantlingItem).where(
        DismantlingItem.vehicle_id==v.id,DismantlingItem.account_id==who.workspace_account_id,
        DismantlingItem.source=='carpot.catalogue.v1'))} if state else {}
    from app.services.dismantling_plan_v3 import generator_basis
    return dict(selection_basis=generator_basis(v),selection=(v.dismantling_v3 or {}).get('global_selection'),saved=state,
        keys=keys,legacy=bool(not state and (v.dismantling_v3 or v.ktype)),
        legacy_source='base' if (v.dismantling_v3 or {}).get('unified_base') else 'professional')


from app.schemas.orders import Key
class ExistingVehicleSelection(Input):
    request_key: Key
    source_modification_id: int = Field(strict=True,gt=0)
    model_id: int = Field(strict=True,gt=0)
    manufacturer_id: int = Field(strict=True,gt=0)
    source_snapshot_sha: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_basis: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirm_exact_modification: bool = False


@router.post('/{id}/catalogue-selection')
def select_existing_vehicle(id:str,data:ExistingVehicleSelection,db:DB,who:Auth):
    """Attach an explicitly confirmed source identity; never create a second donor."""
    from sqlalchemy import select
    from app.models import DismantlingItem
    from app.services.dismantling_plan_v3 import generator_basis,replay,finish
    from app.services.inventory import snapshot,record
    require_permission(who,'vehicles.view','vehicles.edit','catalog.view','dismantling.manage')
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    prior,sha=replay(db,v,who,data,'catalogue-selection')
    if prior is not None:return prior
    if not data.confirm_exact_modification:raise HTTPException(422,'Підтвердіть конкретну модифікацію; VIN не доводить джерельний ID')
    if data.expected_basis!=generator_basis(v):raise HTTPException(409,'Характеристики автомобіля змінилися. Повторіть вибір модифікації')
    old=(v.dismantling_v3 or {}).get('global_selection')
    has_items=db.scalar(select(DismantlingItem.id).where(DismantlingItem.account_id==who.workspace_account_id,DismantlingItem.vehicle_id==v.id).limit(1))
    same=bool(old and (old['car_id'],old['model_id'],old['manufacturer_id'],old['source_snapshot_sha'])==(data.source_modification_id,data.model_id,data.manufacturer_id,data.source_snapshot_sha))
    if (old and not same) or (has_items and (not same or old.get('identity_fingerprint')!=generator_basis(v))):
        raise HTTPException(409,'Наявний план збережено. Зміна джерельної модифікації потребує окремої звірки без перезапису позицій')
    try:
        plan=service.CatalogueAdapter().plan(data.source_modification_id,global_source=True)
        service.validate_plan(plan['payload'])
        entries=service.CatalogueAdapter().directory(car_id=data.source_modification_id)['items']
        entry=next((r for r in entries if r['source_modification_id']==data.source_modification_id),None)
    except (service.CatalogueUnavailable,ValueError,KeyError,TypeError):
        raise HTTPException(503,'Не вдалося перевірити точну модифікацію каталогу') from None
    expected=(data.source_modification_id,data.model_id,data.manufacturer_id,data.source_snapshot_sha)
    payload=plan['payload']
    if not entry or not payload['categories'] or (payload['car_id'],payload['model_id'],payload['manufacturer_id'],payload['source_snapshot_sha'])!=expected or (entry['source_modification_id'],entry['model_id'],entry['manufacturer_id'],entry['snapshot_sha'])!=expected:
        raise HTTPException(409,'Джерельні ID або версія каталогу змінилися')
    # Exact normalized maker guard only. Model names never select a source car ID.
    normalized=lambda value:''.join(c for c in value.casefold() if c.isalnum())
    if normalized(v.manufacturer)!=normalized(entry['manufacturer']):raise HTTPException(409,'Марка джерельної модифікації не відповідає автомобілю')
    before=snapshot(v)
    v.dismantling_v3={**(v.dismantling_v3 or {}),'global_selection':dict(car_id=data.source_modification_id,model_id=data.model_id,manufacturer_id=data.manufacturer_id,source_snapshot_sha=data.source_snapshot_sha,modification_description=payload['modification'].get('description'),source_specifications=entry.get('specifications',[])[:100],vehicle_basis=service.vehicle_basis(v),identity_fingerprint=generator_basis(v),request_key=data.request_key,confirmation='explicit_user_source_identity_not_vin_verified')}
    record(db,who.workspace_account_id,v,'vehicle_update','Підтверджено джерельну модифікацію; VIN, характеристики й склад не змінено',before)
    result=finish(db,v,who,data,sha,dict(saved=True,vehicle_id=v.id))
    db.commit();return result


def volvo_pilot_payload(v, source_modification_id, snapshot_sha=None):
    """Only the verified source identity of this pilot, not VIN fitment."""
    import re
    if v.manufacturer.strip().casefold() != 'volvo' or not re.search(r'\bXC90\b', v.model, re.IGNORECASE):
        raise HTTPException(409, 'Пілот OEM доступний лише для Volvo XC90')
    if source_modification_id != 107555:
        raise HTTPException(422, 'Для пілота доступна лише модифікація 107555')
    try:
        payload = service.CatalogueAdapter().plan(source_modification_id)['payload']
        service.validate_plan(payload)
        if (payload['car_id'], payload['model_id'], payload['manufacturer_id']) != (107555, 13084, 120):
            raise ValueError('source identity')
    except (service.CatalogueUnavailable, ValueError, KeyError, TypeError):
        raise HTTPException(503, 'Каталог Volvo тимчасово недоступний; план збережено') from None
    if snapshot_sha is not None and snapshot_sha != payload['source_snapshot_sha']:
        raise HTTPException(409, 'Версія каталогу змінилася. Оновіть попередній перегляд')
    return payload


def volvo_row_basis(row):
    from app.services.catalogue_format import digest
    return digest([row.id,row.source,row.catalog_key,row.name,row.position,row.category_name,
                   row.subcategory_name,row.included,row.part_id,row.status,
                   row.assembly_consumed_operation_id])


def volvo_references(v):
    return (v.dismantling_v3 or {}).get('volvo_oem_references', {})


@router.get('/{id}/volvo-oem-preview')
def volvo_oem_preview(
    id: str, db: DB, who: Auth,
    source_modification_id: int = Query(gt=0),
    product_id: int | None = Query(None, gt=0),
    snapshot_sha: str | None = Query(None, pattern=r'^[a-f0-9]{64}$'),
):
    """Read-only comparison with a pinned Catalogue source."""
    from sqlalchemy import select
    from app.models import DismantlingItem, Part
    from app.services.dismantling_plan_v3 import generator_basis
    from app.services.catalogue_format import digest
    require_permission(who, 'vehicles.view', 'catalog.view', 'inventory.view')
    v = owned(db, Vehicle, id, who.workspace_account_id)
    if product_id is not None and snapshot_sha is None:
        raise HTTPException(422, 'Потрібна версія каталогу з попереднього перегляду')
    payload = volvo_pilot_payload(v, source_modification_id, snapshot_sha)
    sha = payload['source_snapshot_sha']
    basis = generator_basis(v)
    base = dict(source_modification_id=107555, model_id=13084, snapshot_sha=sha,
                vehicle_basis=basis, modification=payload['modification'], coverage=payload['coverage'],
                observed_at=payload['observed_at'], vin_verified=False, cost='free')
    if product_id is not None:
        product = next((p for p in payload['categories'] if p['product_id'] == product_id), None)
        if product is None:
            raise HTTPException(404, 'Тип запчастини відсутній у цій модифікації')
        offers = saved_articles(product, {'payload': payload}, oem_manufacturer_id=120)
        return dict(**base, product_id=product_id, articles=[
            {k: offer[k] for k in ('supplier_id','article_nr','brand','oem_numbers','vin_verified')}
            for offer in offers
        ])
    rows = list(db.scalars(select(DismantlingItem).where(
        DismantlingItem.account_id == who.workspace_account_id,
        DismantlingItem.vehicle_id == v.id,
    ).order_by(DismantlingItem.name, DismantlingItem.id)))
    parts = {p.id:p for p in db.scalars(select(Part).where(
        Part.account_id==v.account_id,Part.vehicle_id==v.id,
        Part.id.in_([row.part_id for row in rows if row.part_id])))}
    references = volvo_references(v)
    def row_view(row):
        ref=references.get(row.id)
        part=parts.get(row.part_id)
        return dict(id=row.id,name=row.name,position=row.position,
                    category=row.category_name,subcategory=row.subcategory_name,
                    included=row.included,part_id=row.part_id,row_basis=volvo_row_basis(row),
                    reference=ref,reference_digest=digest(ref),
                    reference_stale=bool(ref and (ref['vehicle_basis']!=basis or ref['snapshot_sha']!=sha)),
                    stock_oem=part.oem_number if part else None,
                    stock_eligible=bool(part and not part.archived and part.quantity>0 and not part.reserved_quantity
                        and not part.oem_number and not part.oem_provenance and not row.assembly_consumed_operation_id))
    return dict(**base, plan_items=[row_view(row) for row in rows],
        catalogue_types=[dict(product_id=p['product_id'], name_uk=p.get('name_uk'),
                              name_source=p.get('name_source'), category_path=p.get('category_path'),
                              article_count=p['article_count'], kind=p['kind'])
                         for p in payload['categories']])


class VolvoOemSelection(Input):
    request_key: Key
    source_modification_id: int = Field(strict=True,gt=0)
    snapshot_sha: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_vehicle_basis: str = Field(pattern=r'^[a-f0-9]{64}$')
    item_id: str = Field(min_length=1,max_length=36)
    expected_row_basis: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_reference_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    product_id: int = Field(strict=True,gt=0)
    supplier_id: int = Field(strict=True,gt=0)
    article_number: str = Field(min_length=1,max_length=150)
    oem_number: str = Field(min_length=1,max_length=150)
    confirm_reference: bool = False
    assign_stock: bool = False
    confirm_physical_oem: bool = False


@router.post('/{id}/volvo-oem-selection')
def save_volvo_oem(id: str, data: VolvoOemSelection, db: DB, who: Auth):
    """Explicit cross-reference selection, separate from physical receipt."""
    from sqlalchemy import select
    from app.models import DismantlingItem, Part
    from app.services.inventory import record, snapshot
    from app.services.dismantling_plan_v3 import generator_basis, replay, finish
    from app.services.catalogue_format import digest
    require_permission(who,'vehicles.view','catalog.view','inventory.view','dismantling.manage')
    if data.assign_stock:
        require_permission(who,'inventory.edit')
    if not data.confirm_reference or (data.assign_stock and not data.confirm_physical_oem):
        raise HTTPException(422,'Підтвердіть каталожний вибір і, для складу, номер фактичної деталі')
    v=owned(db,Vehicle,id,who.workspace_account_id,lock=True,active=True)
    prior,request_sha=replay(db,v,who,data,'volvo-oem-selection')
    if prior is not None:return prior
    basis=generator_basis(v)
    if data.expected_vehicle_basis!=basis:
        raise HTTPException(409,'Характеристики автомобіля змінилися. Оновіть перегляд')
    row=db.scalar(select(DismantlingItem).where(DismantlingItem.id==data.item_id,
        DismantlingItem.account_id==v.account_id,DismantlingItem.vehicle_id==v.id).with_for_update())
    if row is None:raise HTTPException(404,'Позицію плану не знайдено')
    refs=volvo_references(v)
    if volvo_row_basis(row)!=data.expected_row_basis or digest(refs.get(row.id))!=data.expected_reference_digest:
        raise HTTPException(409,'Позиція або OEM змінилися. Оновіть перегляд')
    if not row.included or row.status=='absent' or row.assembly_consumed_operation_id:
        raise HTTPException(409,'Виключена, відсутня або спожита позиція недоступна для призначення')
    payload=volvo_pilot_payload(v,data.source_modification_id,data.snapshot_sha)
    product=next((p for p in payload['categories'] if p['product_id']==data.product_id),None)
    if not product or product.get('kind')!='part':
        raise HTTPException(422,'Потрібен перевірений тип деталі каталогу')
    offers=saved_articles(product,{'payload':payload},oem_manufacturer_id=120)
    offer=next((o for o in offers if o['supplier_id']==data.supplier_id and o['article_nr']==data.article_number),None)
    if not offer or not offer['brand'] or data.oem_number not in offer['oem_numbers']:
        raise HTTPException(422,'OEM Volvo відсутній у підтвердженому джерелі')
    ref=dict(source='carpot.catalogue',status='user_selected_cross_reference',vin_verified=False,
        source_modification_id=107555,oem_manufacturer_id=120,product_id=data.product_id,
        supplier_id=data.supplier_id,source_article=data.article_number,source_brand=offer['brand'],
        oem_number=data.oem_number,snapshot_sha=data.snapshot_sha,observed_at=payload['observed_at'],
        vehicle_basis=basis)
    stock=False
    if data.assign_stock:
        if not row.part_id:raise HTTPException(409,'Спочатку оприбуткуйте фактичну деталь')
        p=owned(db,Part,row.part_id,v.account_id,lock=True,active=True)
        if p.vehicle_id!=v.id or p.quantity<=0 or p.reserved_quantity or p.oem_number or p.oem_provenance:
            raise HTTPException(409,'Складська картка змінилася або вже має OEM; наявні дані збережено')
        before=snapshot(p)
        p.oem_number=data.oem_number
        p.oem_provenance={**ref,'physical_number_confirmed_by_user':True,'plan_item_id':row.id}
        record(db,v.account_id,p,'part_update','Явно підтверджено OEM Volvo фактичної деталі',before)
        stock=True
    if refs.get(row.id)!=ref:
        before=snapshot(v)
        v.dismantling_v3={**(v.dismantling_v3 or {}),'volvo_oem_references':{**refs,row.id:ref}}
        record(db,v.account_id,v,'vehicle_update','Збережено довідковий OEM позиції плану; без зміни залишків',before)
    result=finish(db,v,who,data,request_sha,dict(saved=True,item_id=row.id,reference=ref,stock_assigned=stock))
    db.commit()
    return result
