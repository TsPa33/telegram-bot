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


def saved_articles(product, state):
    payload=state['payload']
    if payload.get('schema')=='carpot.volvo.plan.v2':
        try:
            items=service.CatalogueAdapter().articles(payload['car_id'],product['product_id'],payload['source_snapshot_sha'])
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
            oem_numbers=sorted({str(source_value(r,'OENbr')) for r in item.get('oem',[]) if source_value(r,'OENbr')}),
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
