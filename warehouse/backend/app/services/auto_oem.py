"""Automatic free catalogue OEM enrichment, independent of browser sessions.

Existing JSON/provenance fields only. References are cross-reference defaults,
not verified physical OE or VIN fitment. No paid calls, stock ledger, schema,
prices or user notifications. The legacy JSON key is retained for compatibility.
"""
import logging
import os
import re
import threading
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


def valid_reference(v,row,ref):
    return reference_matches(ref,row,basis(v)) and ('engine_variant' not in ref or ref['engine_variant']==normalized(v.engine_variant))

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

def position_tags(value):
    value=normalized(value)
    tags=set()
    for tag,pattern in [('front',r'\b(?:передн\w*|front)\b'),('rear',r'\b(?:задн\w*|rear)\b'),
                        ('left',r'\b(?:лів\w*|лев\w*|слева|left)\b'),('right',r'\b(?:прав\w*|справа|right)\b')]:
        if re.search(pattern,value):tags.add(tag)
    return tags

def placement_ok(row,product,offer):
    if row is None:return True
    required=position_tags((row.name or '')+' '+(getattr(row,'position','') or ''))
    if not required:return True
    type_tags=position_tags((product or {}).get('name_uk') or '')
    explicit=set()
    for attr in offer.get('source_attributes',[]):
        if not isinstance(attr,dict):continue
        keys={str(k).casefold():v for k,v in attr.items()}
        label=normalized(str(keys.get('description') or keys.get('displaytitle') or ''))
        if str(keys.get('id'))=='100' or any(t in label for t in ('сторона установки','місце встановлення','місце установки','fitting position','installation position')):
            explicit|=position_tags(str(keys.get('displayvalue') or ''))
    for axis in ({'front','rear'},{'left','right'}):
        want=required&axis
        if want and not want.issubset((explicit&axis) or (type_tags&axis)):return False
    return True

def choices(offers,part=None,row=None,product=None):
    evidence={}
    for offer in offers:
        if not offer.get('brand') or not offer.get('article_nr'):continue
        if not placement_ok(row,product,offer):continue
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
    return result if len(result)<=1000 else []

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
        vehicle_basis=basis(v),engine_variant=normalized(v.engine_variant),row_identity=row_identity(row),alternatives=alternatives,selection_rule=RULE)

def fill_part(db,v,row,part,ref,*,receipt=False):
    """Copy the reference only to a genuinely empty card; never overwrite a manual clear.
    If an article was set, require matching supplier+article evidence.
    """
    if not ref or ref.get('oem_number') not in options(ref) or not valid_reference(v,row,ref) or part.oem_number or part.oem_provenance or part.archived or part.reserved_quantity:return False
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
        self.plans={};self.offers={};self.exact={};self.lock=threading.Lock();self.directory=None
    def resolve_directory(self,v):
        """Unique exact maker/model/engine/year match among published snapshots."""
        code=lambda s:''.join(c for c in normalized(s) if c.isalnum())
        engine=code(v.engine_code)
        if not engine:return None
        if self.directory is None:
            entries=[];cursor=0
            for _ in range(100):
                result=self.adapter.directory(after=cursor)
                entries.extend(result['items'])
                nxt=result.get('next_after')
                if nxt is None:break
                if type(nxt) is not int or nxt<=cursor:raise catalogue.CatalogueUnavailable('invalid_directory_cursor')
                cursor=nxt
            else:raise catalogue.CatalogueUnavailable('directory_limit')
            self.directory=entries
        maker=code(v.manufacturer);model=code(v.model)
        models={model}
        if v.generation and normalized(v.generation)!='не уточнено':models.add(code(v.model+' '+v.generation))
        candidates=[]
        for e in self.directory:
            if code(e.get('manufacturer'))!=maker or code(e.get('model')) not in models:continue
            attrs={a.get('attributetype'):str(a.get('displayvalue') or '') for a in e.get('specifications',[]) if isinstance(a,dict)}
            if code(attrs.get('EngineCode'))!=engine:continue
            interval=attrs.get('ConstructionInterval') or e.get('modification',{}).get('constructioninterval') or ''
            years=[int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b',interval)]
            if not years or v.year<years[0] or (len(years)>1 and v.year>years[-1]):continue
            fuel=normalized(v.fuel_type);source_fuel=normalized(attrs.get('FuelType'))
            drive=normalized(v.drive_type);source_drive=normalized(attrs.get('DriveType'))
            fuel_groups=[{'petrol','gasoline','бензин','gas'},{'diesel','дизель','дизельное топливо'},{'hybrid','гібрид','гибрид'},{'electric','електро','электричество'}]
            drive_groups=[{'awd','4wd','full','повний','повний (awd)','привод на все колеса','all-wheel drive'},{'fwd','front','передній','передній (fwd)','передний привод','front-wheel drive'},{'rwd','rear','задній','задній (rwd)','задний привод','rear-wheel drive'}]
            if fuel and not (fuel==source_fuel or any(fuel in g and source_fuel in g for g in fuel_groups)):continue
            if drive and not (drive==source_drive or any(drive in g and source_drive in g for g in drive_groups)):continue
            variant=code(v.engine_variant)
            if variant and variant not in code(e.get('modification',{}).get('description')):continue
            if v.engine_displacement_l is not None:
                capacity=re.fullmatch(r'([0-9]+(?:[.,][0-9]+)?)\s*l',attrs.get('Capacity','').strip(),re.I)
                if not capacity or abs(float(capacity[1].replace(',','.'))-float(v.engine_displacement_l))>.05:continue
            sha=e.get('snapshot_sha')
            if not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{64}',sha):continue
            ids=(e.get('source_modification_id'),e.get('model_id'),e.get('manufacturer_id'))
            if all(type(n) is int and n>0 for n in ids):candidates.append((*ids,sha,True))
        return candidates[0] if len(candidates)==1 else None

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
        with self.lock:
            if key in self.offers:return self.offers[key]
        offers=saved_articles(product,{'payload':payload},oem_manufacturer_id=payload['manufacturer_id'],adapter=self.adapter)
        with self.lock:
            if len(self.offers)>=512:self.offers.clear()
            self.offers[key]=offers
        return offers

    def exact_lookup(self,make,brand,article,supplier_id):
        key=(make,brand,article,supplier_id)
        with self.lock:
            if key in self.exact:return self.exact[key]
        try:result=self.adapter.exact_oem(make,brand,article,supplier_id)
        except catalogue.CatalogueUnavailable:
            # Compatibility while the older Catalogue service is deployed:
            # only Volvo and only when an exact supplier ID is already available.
            if normalized(make)!='volvo' or not supplier_id:return None
            try:result={**self.adapter.article(supplier_id,article,brand),'manufacturer_id':120,
                        'supplier_id':supplier_id,'supplier_name':brand,'article_number':article}
            except catalogue.CatalogueUnavailable:return None
            if result.get('truncated'):return None
        with self.lock:
            if len(self.exact)>=512:self.exact.clear()
            self.exact[key]=result
        return result

def exact_key(part,vehicle):
    if not eligible_part(part) or not part.article_number or not part.article_brand or len(part.article_number)>32:return None
    sid=(part.article_provenance or {}).get('supplier_id')
    if type(sid) is not int or not 1<=sid<=65535:sid=None
    return (vehicle.manufacturer,part.article_brand,part.article_number,sid)

def fill_exact(db,v,part,result):
    numbers=sorted(set(result.get('oem_numbers',[])))
    if not numbers or len(numbers)>1000 or any(not isinstance(n,str) or not n or len(n)>150 for n in numbers):return False
    alternatives=[dict(oem_number=n,supplier_id=result['supplier_id'],source_article=result['article_number'],source_brand=result['supplier_name']) for n in numbers]
    before=snapshot(part);part.oem_number=numbers[0]
    part.oem_provenance=dict(**alternatives[0],source='carpot.catalogue',status='auto_selected_cross_reference',
        vin_verified=False,oem_manufacturer_id=result['manufacturer_id'],vehicle_basis=basis(v),
        alternatives=alternatives,selection_rule='exact_supplier_article_lexical')
    record(db,v.account_id,part,'part_update','Каталожний OEM',before,after_extra={'automatic_oem':True})
    return True

def enrich_vehicle(engine,account_id,vehicle_id,cache=None):
    """Network outside write locks; recheck all identities before committing.
    Existing and new donors, including unlinked stock and all makes with exact articles.
    """
    cache=cache or SourceCache()
    with Session(engine) as db:
        v=db.scalar(select(Vehicle).where(Vehicle.id==vehicle_id,Vehicle.account_id==account_id,Vehicle.archived.is_(False)))
        if not v:return 0
        identity=source_identity(v);direct_identity=identity;old_basis=basis(v);old_variant=normalized(v.engine_variant)
        rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==v.id,DismantlingItem.account_id==account_id)))
        old_refs=references(v)
        linked={p.id:p for p in db.scalars(select(Part).where(Part.vehicle_id==v.id,Part.account_id==account_id))}
        exact={p.id:k for p in linked.values() if (k:=exact_key(p,v))}
        needs=[r for r in rows if eligible_row(r) and (r.id not in old_refs or not options(old_refs[r.id]) or (r.part_id in linked and eligible_part(linked[r.part_id])))]
        if not exact and not needs:return 0
    if identity is None and needs and not ((v.dismantling_v3 or {}).get('global_selection') or catalogue.saved_state(v)):
        try:identity=cache.resolve_directory(v)
        except catalogue.CatalogueUnavailable:pass
    if not exact and not identity:return 0
    payload=None;products={};data={};exact_data={}
    if identity and needs:
        try:
            payload=cache.plan(identity);products={p['product_id']:p for p in payload['categories']}
            needed={}
            for row in needs:
                p=matches(row,products,payload['car_id'])
                if p:needed[p['product_id']]=p
            def offers_for(product):
                try:return cache.get_offers(payload,product)
                except Exception:return None
            with ThreadPoolExecutor(max_workers=4) as pool:
                data={pid:offers for pid,offers in zip(needed,pool.map(offers_for,needed.values())) if offers is not None}
        except Exception:
            # Exact-article lookup remains independent of snapshot availability.
            log.warning('OEM snapshot lookup deferred for donor %s',vehicle_id)
            payload=None;products={};data={}
    if exact:
        unique=list(set(exact.values()))
        with ThreadPoolExecutor(max_workers=4) as pool:
            exact_data=dict(zip(unique,pool.map(lambda k:cache.exact_lookup(*k),unique)))
    if not payload and not any(exact_data.values()):return 0
    with Session(engine) as db:
        db.execute(text("SET LOCAL lock_timeout = '2s'"))
        db.scalar(select(Account).where(Account.id==account_id).with_for_update(key_share=True))
        v=db.scalar(select(Vehicle).where(Vehicle.id==vehicle_id,Vehicle.account_id==account_id,Vehicle.archived.is_(False)).with_for_update())
        if not v or basis(v)!=old_basis or normalized(v.engine_variant)!=old_variant or source_identity(v)!=direct_identity:return 0
        rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==v.id,DismantlingItem.account_id==account_id).order_by(DismantlingItem.id).with_for_update()))
        parts={p.id:p for p in db.scalars(select(Part).where(Part.vehicle_id==v.id,Part.account_id==account_id).order_by(Part.id).with_for_update())}
        refs=dict(references(v));added=0;changed=False;stock_changes=0
        before=snapshot(v)
        for pid,key in exact.items():
            part=parts.get(pid);result=exact_data.get(key)
            if part and result and exact_key(part,v)==key and fill_exact(db,v,part,result):stock_changes+=1
        if payload:
            for row in rows:
                if not eligible_row(row):continue
                product=matches(row,products,payload['car_id']);part=parts.get(row.part_id);ref=refs.get(row.id)
                if ref:
                    if not options(ref) and product and valid_reference(v,row,ref) and ref.get('snapshot_sha')==payload['source_snapshot_sha'] and ref.get('product_id')==product['product_id']:
                        alternatives=choices(data.get(product['product_id'],[]),row=row,product=product)
                        if ref['oem_number'] in [a['oem_number'] for a in alternatives]:
                            ref={**ref,'alternatives':alternatives};refs[row.id]=ref;changed=True
                elif product and product['product_id'] in data:
                    alternatives=choices(data[product['product_id']],part,row,product)
                    if not alternatives:continue
                    # Preserve a stock OEM, but mirror its matching reference if available.
                    if part and (part.oem_number or part.oem_provenance):
                        match=next((a for a in alternatives if a['oem_number']==part.oem_number),None)
                        if not match:continue
                        alternatives=[match,*[a for a in alternatives if a!=match]]
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
