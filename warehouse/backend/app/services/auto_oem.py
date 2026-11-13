"""Automatic free catalogue OEM enrichment, independent of browser sessions.

Existing JSON/provenance fields only. References are cross-reference defaults,
not verified physical OE or VIN fitment. No paid calls, stock ledger, schema,
prices or user notifications. The legacy JSON key is retained for compatibility.
"""
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select,text,create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from app.models import Vehicle,DismantlingItem,Part,Account
from app.services import unified_catalogue as catalogue
from app.services.dismantling_plan_v3 import generator_basis
from app.services.volvo_oem_review import overlay,normalized,row_identity,reference_matches
from app.services.inventory import record,snapshot
from app.config import database_url,is_staging

log=logging.getLogger(__name__)
LOCK=734259016351
REF_KEY='volvo_oem_references' # historical persisted key; now all manufacturers
RULE='supplier_support_then_lexical'

def basis(v):
    return generator_basis(v)

def source_identity(v):
    """Only a pinned source selection or an evidence-specific Volvo pilot match.
    Never infer another make/model's modification from its name alone.
    """
    state=v.dismantling_v3 or {}
    selection=state.get('global_selection')
    saved=catalogue.saved_state(v)
    if selection:
        if selection.get('vehicle_basis')!=catalogue.vehicle_basis(v) or (selection.get('identity_fingerprint') and selection['identity_fingerprint']!=basis(v)):
            return None
        if saved and (catalogue.needs_review(v) or saved['payload']['car_id']!=selection.get('car_id')):
            return None
        return (selection['car_id'],selection['model_id'],selection['manufacturer_id'],selection['source_snapshot_sha'],True)
    if saved:
        if catalogue.needs_review(v):return None
        p=saved['payload']
        return (p['car_id'],p['model_id'],p['manufacturer_id'],p['source_snapshot_sha'],p.get('schema')=='carpot.vehicle.plan.v1')
    # Source-specific pilot evidence: 2016 XC90 II T6 AWD, B4204T27;
    # the known North American YV4A22PK/G VIN pattern encodes this variant.
    if normalized(v.manufacturer)!='volvo' or not re.search(r'\bxc90\b',v.model,re.I):return None
    if not 2015<=v.year<=2018:return None
    fuel=normalized(v.fuel_type);drive=normalized(v.drive_type);code=normalized(v.engine_code)
    variant=normalized(v.engine_variant)
    if fuel and fuel not in {'petrol','gasoline','бензин','gas'}:return None
    if drive and drive not in {'awd','4wd','full','повний','повний (awd)'}:return None
    if v.engine_displacement_l is not None and float(v.engine_displacement_l)!=2.0:return None
    if code and code!='b4204t27':return None
    if variant and variant not in {'t6','t6 awd','2.0 t6'}:return None
    if normalized(v.generation) not in {'','не уточнено','ii','2','spa','ii (spa)','2 (spa)'}:return None
    vin=(v.vin or '').upper()
    vin_match=v.year==2016 and bool(re.fullmatch(r'YV4A22PK[A-HJ-NPR-Z0-9]G[A-HJ-NPR-Z0-9]{7}',vin))
    if not (code=='b4204t27' or vin_match):return None
    return (107555,13084,120,None,False)

def matches(row,products,car_id):
    # A stable source key outranks exact reviewed labels. No fuzzy matching.
    if getattr(row,'source','')=='carpot.catalogue.v1':
        prefix=f'car:{car_id}:product:'
        key=getattr(row,'catalog_key','')
        if key.startswith(prefix) and key[len(prefix):].isdigit():
            p=products.get(int(key[len(prefix):]))
            return p if p and p.get('kind')=='part' else None
        return None
    name=normalized(row.name)
    found=[]
    for p in products.values():
        if p.get('kind')!='part':continue
        if name not in {normalized(n) for n in [p.get('name_uk'),*p.get('candidate_aliases',[])] if n}:continue
        # Global taxonomy must agree with the existing category; Volvo's pinned
        # reviewed overlay has no reliable category path, so its exact aliases
        # are the reviewed type evidence (not installation/trim evidence).
        path=p.get('category_path') or []
        if not p.get('pilot_reviewed'):
            if len(path)!=3 or not p.get('mapping_reviewed_by'):continue
            if normalized(getattr(row,'category_name',''))!=normalized(path[0]):continue
        found.append(p)
    return found[0] if len(found)==1 else None

def choices(offers,part=None):
    evidence={}
    for offer in offers:
        if not offer.get('brand') or not offer.get('article_nr'):continue
        if part and part.article_number:
            if not part.article_brand or normalized(part.article_brand)!=normalized(offer['brand']) or normalized(part.article_number)!=normalized(offer['article_nr']):continue
        for n in offer.get('oem_numbers',[]):
            n=str(n).strip()
            if not n or len(n)>150:continue
            evidence.setdefault(n,[]).append(offer)
    result=[]
    for n in sorted(evidence,key=lambda n:(-len({o['supplier_id'] for o in evidence[n]}),n)):
        o=min(evidence[n],key=lambda o:(o['supplier_id'],o['article_nr']))
        result.append(dict(oem_number=n,supplier_id=o['supplier_id'],source_article=o['article_nr'],source_brand=o['brand']))
    return result[:200]

def options(ref):
    if not isinstance(ref,dict):return []
    return list(dict.fromkeys(x['oem_number'] for x in ref.get('alternatives',[]) if isinstance(x,dict) and isinstance(x.get('oem_number'),str)))

def references(v):return (v.dismantling_v3 or {}).get(REF_KEY,{})

def eligible_row(row):
    return row.included and row.status!='absent' and not row.assembly_consumed_operation_id

def eligible_part(p):
    return not p.archived and p.quantity>0 and not p.reserved_quantity and p.availability!='absent' and not p.oem_number and not p.oem_provenance

def ref_for(v,row,payload,product,alternatives):
    return dict(**alternatives[0],source='carpot.catalogue',status='auto_selected_cross_reference',
        vin_verified=False,source_modification_id=payload['car_id'],oem_manufacturer_id=payload['manufacturer_id'],
        product_id=product['product_id'],snapshot_sha=payload['source_snapshot_sha'],observed_at=payload['observed_at'],
        vehicle_basis=basis(v),row_identity=row_identity(row),alternatives=alternatives,selection_rule=RULE)

def fill_part(db,v,row,part,ref,*,receipt=False):
    """Copy the reference only to a genuinely empty card; never overwrite a manual clear.
    If an article was set, require matching supplier+article evidence.
    """
    if not ref or not reference_matches(ref,row,basis(v)) or part.oem_number or part.oem_provenance or part.archived or part.reserved_quantity:return False
    if not receipt and not eligible_part(part):return False
    if part.vehicle_id!=v.id or part.account_id!=v.account_id:return False
    if part.article_number and (not part.article_brand or normalized(part.article_brand)!=normalized(ref.get('source_brand')) or normalized(part.article_number)!=normalized(ref.get('source_article'))):return False
    before=snapshot(part)
    part.oem_number=ref['oem_number']
    part.oem_provenance={**ref,'plan_item_id':row.id,'physical_number_confirmed_by_user':False}
    record(db,v.account_id,part,'part_update','Каталожний OEM',before,after_extra={'automatic_oem':True})
    return True

def receipt_oem(db,row,part):
    v=db.get(Vehicle,row.vehicle_id)
    if v and v.account_id==row.account_id:
        return fill_part(db,v,row,part,references(v).get(row.id),receipt=True)
    return False

class SourceCache:
    def __init__(self,adapter=None):
        self.adapter=adapter or catalogue.CatalogueAdapter()
        self.plans={};self.offers={}
    def plan(self,identity):
        car,model,make,sha,global_source=identity
        if identity not in self.plans:
            p=self.adapter.plan(car,global_source=global_source)['payload']
            catalogue.validate_plan(p)
            if (p['car_id'],p['model_id'],p['manufacturer_id'])!=(car,model,make) or (sha and sha!=p['source_snapshot_sha']):raise catalogue.CatalogueUnavailable('identity_changed')
            if car==107555 and make==120:p=overlay(p)
            if len(self.plans)>=32:self.plans.clear()
            self.plans[identity]=p
        return self.plans[identity]
    def get_offers(self,payload,product):
        from app.api.unified_catalogue import saved_articles
        key=(payload['car_id'],payload['source_snapshot_sha'],product['product_id'])
        if key not in self.offers:
            # Use the existing validated article contract with the same adapter.
            # Test adapters may supply fixtures; the real adapter is constructed in saved_articles.
            offers=saved_articles(product,{'payload':payload},oem_manufacturer_id=payload['manufacturer_id'])
            if len(self.offers)>=512:self.offers.clear()
            self.offers[key]=offers
        return self.offers[key]

def enrich_vehicle(engine,account_id,vehicle_id,cache=None):
    """Network outside write locks, then recheck donor/type/part identities under lock.
    Called for every active donor, including those created since the previous sweep.
    """
    cache=cache or SourceCache()
    with Session(engine) as db:
        v=db.scalar(select(Vehicle).where(Vehicle.id==vehicle_id,Vehicle.account_id==account_id,Vehicle.archived.is_(False)))
        if not v:return 0
        identity=source_identity(v)
        if not identity:return 0
        old_basis=basis(v)
        rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==v.id,DismantlingItem.account_id==account_id)))
        if not rows:return 0
        old_refs=references(v)
        linked={p.id:p for p in db.scalars(select(Part).where(Part.vehicle_id==v.id,Part.account_id==account_id))}
        needs=[r for r in rows if eligible_row(r) and (r.id not in old_refs or not options(old_refs[r.id]) or (r.part_id in linked and eligible_part(linked[r.part_id])))]
        if not needs:return 0
    payload=cache.plan(identity)
    products={p['product_id']:p for p in payload['categories']}
    needed={}
    for row in needs:
        p=matches(row,products,payload['car_id'])
        if p:needed[p['product_id']]=p
    # Bounded network fanout; a failed source never produces partial invented numbers.
    with ThreadPoolExecutor(max_workers=4) as pool:
        data=dict(zip(needed,pool.map(lambda p:cache.get_offers(payload,p),needed.values())))
    with Session(engine) as db:
        db.execute(text("SET LOCAL lock_timeout = '2s'"))
        db.scalar(select(Account).where(Account.id==account_id).with_for_update(key_share=True))
        v=db.scalar(select(Vehicle).where(Vehicle.id==vehicle_id,Vehicle.account_id==account_id,Vehicle.archived.is_(False)).with_for_update())
        if not v or basis(v)!=old_basis or source_identity(v)!=identity:return 0
        rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==v.id,DismantlingItem.account_id==account_id).order_by(DismantlingItem.id).with_for_update()))
        parts={p.id:p for p in db.scalars(select(Part).where(Part.vehicle_id==v.id,Part.account_id==account_id,Part.id.in_([r.part_id for r in rows if r.part_id])).order_by(Part.id).with_for_update())}
        refs=dict(references(v));added=0;changed=False;stock_changes=0
        before=snapshot(v)
        for row in rows:
            if not eligible_row(row):continue
            product=matches(row,products,payload['car_id'])
            part=parts.get(row.part_id)
            ref=refs.get(row.id)
            if ref:
                # Preserve all prior user-selected/automatic codes; enrich their
                # alternatives only when the same number is present in the same source.
                if not options(ref) and product and reference_matches(ref,row,old_basis) and ref.get('snapshot_sha')==payload['source_snapshot_sha'] and ref.get('product_id')==product['product_id']:
                    alternatives=choices(data.get(product['product_id'],[]))
                    if ref['oem_number'] in [a['oem_number'] for a in alternatives]:
                        ref={**ref,'alternatives':alternatives};refs[row.id]=ref;changed=True
            elif product and product['product_id'] in data:
                if part and (part.oem_number or part.oem_provenance):continue
                alternatives=choices(data[product['product_id']],part)
                if not alternatives:continue
                ref=ref_for(v,row,payload,product,alternatives);refs[row.id]=ref;added+=1;changed=True
            if ref and part and fill_part(db,v,row,part,ref):stock_changes+=1
        if changed:
            v.dismantling_v3={**(v.dismantling_v3 or {}),REF_KEY:refs}
            record(db,account_id,v,'vehicle_update','Каталожні OEM',before,after_extra={'automatic_oem':True})
        db.commit()
        return added+stock_changes

def sweep(engine,stop,cache=None):
    cache=cache or SourceCache()
    cursor=''
    while not stop.is_set():
        with Session(engine) as db:
            page=db.execute(select(Vehicle.id,Vehicle.account_id).where(Vehicle.id>cursor,Vehicle.archived.is_(False)).order_by(Vehicle.id).limit(20)).all()
        if not page:return
        for vid,aid in page:
            if stop.is_set():return
            try:enrich_vehicle(engine,aid,vid,cache)
            except Exception:log.warning('Automatic OEM enrichment deferred for donor %s',vid,exc_info=True)
            cursor=vid
        stop.wait(.1)

def start_worker():
    stop=threading.Event()
    enabled=os.getenv('WAREHOUSE_AUTO_OEM_ENABLED','true' if is_staging() else 'false').lower()=='true'
    if not enabled or not os.getenv('WAREHOUSE_CATALOGUE_URL') or not os.getenv('WAREHOUSE_CATALOGUE_KEY'):return stop,None
    def loop():
        e=create_engine(database_url(),poolclass=NullPool)
        try:
            while not stop.is_set():
                try:
                    with e.connect() as conn:
                        locked=conn.scalar(text('SELECT pg_try_advisory_lock(:key)'),{'key':LOCK});conn.commit()
                        if locked:
                            try:sweep(e,stop)
                            finally:conn.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':LOCK});conn.commit()
                except Exception:log.exception('Automatic OEM sweep deferred')
                stop.wait(120)
        finally:e.dispose()
    thread=threading.Thread(target=loop,name='warehouse-auto-oem',daemon=True);thread.start()
    return stop,thread
