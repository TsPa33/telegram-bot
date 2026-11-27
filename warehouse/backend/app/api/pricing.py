from fastapi import APIRouter,HTTPException,Query
from sqlalchemy import select,text
from app.api.routes import DB,Auth
from app.api.secure_route import SecureRoute
from app.models import Vehicle,Part,PriceDecision
from app.services.inventory import owned
from app.services.virtual_inventory import lock_workspace
from app.services.catalogue_import import LOCK
from app.services import pricing
from app.services.price_guidance import parts_for,guidance
from app.schemas import Input
from app.schemas.pricing import PriceBatch,PricePreview,PriceApply
router=APIRouter(route_class=SecureRoute,prefix='/api/v1',tags=['Market and seller prices'])

def catalogue_lock(db):
    if not db.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':LOCK}):raise HTTPException(409,'Каталог оновлюється; повторіть перевірку після завершення')

@router.get('/parts/{id}/price-guidance')
def single(id:str,db:DB,who:Auth):
    parts=parts_for(db,who.workspace_account_id,[id]);market=guidance(db,parts,who.workspace_account_id)
    return {**market[id],'part_revision':pricing.revisions(db,parts)[id]}

@router.post('/pricing/guidance')
def batch(data:PriceBatch,db:DB,who:Auth):
    parts=parts_for(db,who.workspace_account_id,data.ids);market=guidance(db,parts,who.workspace_account_id);versions=pricing.revisions(db,parts)
    return {'items':[{**market[p.id],'part_revision':versions[p.id]} for p in parts]}

@router.post('/pricing/previews')
def preview(data:PricePreview,db:DB,who:Auth):
    pricing.owner(who);lock_workspace(db,who.workspace_account_id);catalogue_lock(db)
    result=pricing.preview(db,who,data);db.commit();return result

@router.get('/pricing/previews/{id}')
def status(id:str,db:DB,who:Auth):
    pricing.owner(who)
    job=db.scalar(select(PriceDecision).where(PriceDecision.id==id,PriceDecision.account_id==who.workspace_account_id,PriceDecision.actor_id==who.actor_id))
    if not job:raise HTTPException(404,'Перевірку не знайдено')
    return pricing.view(job)

@router.post('/pricing/previews/{id}/apply')
def apply(id:str,data:PriceApply,db:DB,who:Auth):
    pricing.owner(who);lock_workspace(db,who.workspace_account_id)
    result=pricing.apply(db,who,id,data);db.commit();return result

@router.get('/vehicles/{id}/parts-valuation')
def valuation(id:str,db:DB,who:Auth):
    owned(db,Vehicle,id,who.workspace_account_id)
    parts=list(db.scalars(select(Part).where(Part.account_id==who.workspace_account_id,Part.vehicle_id==id,Part.archived.is_(False),Part.assortment_enabled.is_(True),Part.quantity>0).order_by(Part.id).limit(1001)))
    if len(parts)>1000:raise HTTPException(422,'Оцінка підтримує до 1000 активних позицій одного авто')
    return pricing.valuation(db,parts,who.workspace_account_id)

@router.get('/parts/{id}/price-context')
def price_context(id:str,db:DB,who:Auth):
    row=owned(db,Part,id,who.workspace_account_id)
    return dict(part_id=row.id,selling_price=str(row.selling_price) if row.selling_price is not None else None,currency=row.currency,price_token=pricing.revisions(db,[row])[row.id],
                name=row.name,condition=row.condition,eligible=not row.archived and row.assortment_enabled and row.quantity>0)

@router.get('/pricing/selection')
def selection(db:DB,who:Auth,vehicle_id:str|None=None,q:str=Query('',max_length=200),category_id:str|None=None,subcategory_id:str|None=None,manufacturer:str=Query('',max_length=100),model:str=Query('',max_length=100),after_id:str|None=Query(None,max_length=36),condition:str|None=Query(None,max_length=30)):
    from sqlalchemy import or_,func
    pricing.owner(who)
    stmt=select(Part.id).where(Part.account_id==who.workspace_account_id,Part.archived.is_(False),Part.assortment_enabled.is_(True),Part.quantity>0)
    if vehicle_id:owned(db,Vehicle,vehicle_id,who.workspace_account_id);stmt=stmt.where(Part.vehicle_id==vehicle_id)
    if category_id:stmt=stmt.where(Part.category_id==category_id)
    if subcategory_id:stmt=stmt.where(Part.subcategory_id==subcategory_id)
    if manufacturer or model:
        donors=select(Vehicle.id).where(Vehicle.account_id==who.workspace_account_id)
        if manufacturer:donors=donors.where(func.lower(Vehicle.manufacturer)==manufacturer.casefold())
        if model:donors=donors.where(func.lower(Vehicle.model)==model.casefold())
        stmt=stmt.where(Part.vehicle_id.in_(donors))
    if q:stmt=stmt.where(or_(*[column.ilike('%'+q.replace('%',r'\%').replace('_',r'\_')+'%') for column in (Part.name,Part.oem_number,Part.article_number,Part.location,Part.serial_number)]))
    if condition:stmt=stmt.where(Part.condition==condition)
    if after_id:stmt=stmt.where(Part.id>after_id)
    ids=list(db.scalars(stmt.order_by(Part.id).limit(1001)))
    return dict(ids=ids[:1000],truncated=len(ids)>1000,limit=1000,next_after_id=ids[999] if len(ids)>1000 else None)


@router.post('/parts/{id}/market-refresh')
def market_refresh(id:str,data:Input,db:DB,who:Auth):
    # Local catalogue projection only. No network, writes, queue or price mutation.
    from app.services.market_check import check
    from sqlalchemy.exc import DBAPIError
    try:return check(db,who,id)
    except DBAPIError:
        db.rollback()
        raise HTTPException(503,'Локальна перевірка каталогу недоступна або перевищила час очікування. Спробуйте пізніше.') from None


class MarketReferenceInput(Input):
    individual: bool=False


@router.post('/parts/{id}/market-reference')
def market_reference(id:str,data:MarketReferenceInput,db:DB,who:Auth):
    """Stored-only by default. External lookup requires explicit individual intent."""
    from app.services.market_reference_public import public_reference,public_groups
    raw=market_refresh(id,Input(),db,who)
    result=public_reference(raw)
    result["price_mode"]="stored"
    if 'parts.change_price' in who.permissions:
        result["price_token"]=raw["part_revision"]
    from app.services import live_market_reference as live
    result["live_enabled"]=data.individual and live.enabled()
    result["lookup_status"]="stored_only"
    if not data.individual:
        return result
    if not result["live_enabled"]:
        result["lookup_status"]="disabled"
        return result
    from app.services.market_reference_context import lookup_context
    account=who.workspace_account_id
    context=lookup_context(db,account,id)
    # The auth dependency takes a workspace lock for POST. Release the
    # read-only transaction before bounded external I/O.
    db.rollback()
    current=live.lookup(context)
    if not current:
        result["lookup_status"]="unavailable_or_limited"
        return result
    # Recheck identity and authorization after releasing the original locks.
    from app.models import Account,Session,now
    from app.permissions import effective
    user=db.get(Account,who.actor_id)
    session=db.get(Session,who.session.token_hash)
    if not user or not user.is_active or not session or session.expires_at<=now():
        raise HTTPException(401,'Сесію відкликано')
    if (user.workspace_account_id or user.id)!=account or user.must_change_password or not {'inventory.view','catalog.view','market.check'}.issubset(effective(user)):
        raise HTTPException(403,'Доступ змінено')
    if lookup_context(db,account,id)!=context:
        raise HTTPException(409,'Дані деталі змінилися. Повторіть пошук цін.')
    mode,groups,stamp=current
    if mode not in ("live","cached"):
        result["lookup_status"]=mode
        return result
    result["lookup_status"]="matched" if groups else "no_comparable"
    if groups:
        result.update(price_mode=mode,references=public_groups(groups,links=True),historical=[],status="completed",
                      observed_at=stamp,fresh_data_fetched=mode=="live",truncated=False)
    return result
