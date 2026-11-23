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
from app.models import Vehicle,DismantlingItem,Part,Account,Operation,now
from app.models.canonical import CanonicalType
from app.services import unified_catalogue as catalogue
from app.services.dismantling_plan_v3 import generator_basis
from app.services import plan_item_binding
from app.services.catalogue_format import digest
from app.services.volvo_oem_review import overlay,normalized,row_identity,reference_matches
from app.services.inventory import record,snapshot
from app.config import database_url,is_staging

log=logging.getLogger(__name__)
LOCK=734259016351
REF_KEY='volvo_oem_references' # historical persisted key; now all manufacturers
RULE='supplier_support_then_lexical'
IDENTITY_KEY='automatic_catalogue_identity'
CANDIDATES_KEY='other_modification_oems'
AUTO_STATUS='auto_selected_cross_reference'
OUTCOMES_KEY='oem_lookup_outcomes'
ORACLE_LOOKUP_LIMIT=24  # Maximum read-only Oracle lookups per donor enrichment pass.


def oracle_enabled():
    # Explicit staging-only opt-in; production cannot be activated by accident.
    return is_staging() and os.getenv('WAREHOUSE_ORACLE_OEM_ENABLED','false').lower()=='true'

def basis(v):
    return generator_basis(v)


def valid_reference(v,row,ref):
    if not isinstance(ref, dict) or not reference_matches(ref,row,basis(v)):
        return False
    if 'engine_variant' in ref and ref['engine_variant']!=normalized(v.engine_variant):
        return False
    if ref.get('status')=='user_selected_cross_reference' and row.source!='carpot.catalogue.v1':
        return True
    if (ref.get('status')==AUTO_STATUS and
            ref.get('modification_selection')=='auto_assumed' and
            not (v.dismantling_v3 or {}).get('global_selection')):
        return False
    identity=source_identity(v)
    history=(v.dismantling_v3 or {}).get(plan_item_binding.KEY, {}).get(row.id)
    if history:
        active = history[-1] or {}
        if not identity or (active.get('source_modification_id'), active.get('snapshot_sha'), active.get('product_id')) != (
            identity[0], identity[3], ref.get('product_id')
        ):
            return False
    if not identity and ((v.dismantling_v3 or {}).get('global_selection') or catalogue.saved_state(v)):
        return False
    automatic=automatic_identity(v)
    if not identity and automatic:
        identity=(automatic['car_id'],automatic['model_id'],automatic['manufacturer_id'],automatic['snapshot_sha'])
    return not identity or (
        ref.get('source_modification_id')==identity[0]
        and ref.get('oem_manufacturer_id')==identity[2]
        and (not identity[3] or ref.get('snapshot_sha')==identity[3])
    )

def source_identity(v):
    """Only a pinned source selection or an evidence-specific Volvo pilot match.
    Never infer another make/model's modification from its name alone.
    """
    state=v.dismantling_v3 or {}
    selection=state.get('global_selection')
    # The older automatic resolver sometimes saved a T5 plan for a B5 VIN.
    # A saved snapshot is NOT proof of an explicitly verified modification.
    # Do not let its existence bypass the new exact-evidence gate.
    legacy=state.get(IDENTITY_KEY) or {}
    if legacy.get('confirmation')=='auto_assumed' and not selection:
        return None
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
    automatic=automatic_identity(v)
    if automatic:
        return tuple(automatic[k] for k in ('car_id','model_id','manufacturer_id','snapshot_sha','global_source'))
    # Source-specific pilot evidence: 2016 XC90 II T6 AWD, B4204T27;
    # the known North American YV4A22PK/G VIN pattern encodes this variant.
    if normalized(v.manufacturer)!='volvo' or not re.search(r'\bxc90\b',v.model,re.I):return None
    if type(v.year) is not int or not 2015<=v.year<=2018:return None
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

def eligible_product(product):
    # Catalogue stores verified OEM-bearing gaskets, belts, etc. as consumables.
    # They are valid dismantling parts with PRD/article source links too.
    return bool(product and (product.get('kind') in ('part','consumable') or (
        product.get('kind')=='review' and product.get('source_fitment_linked') is True
    )))


def canonical_prd_bindings(db,rows):
    ids={row.plan_v3.get('canonical_part_type_id') for row in rows if row.plan_v3}
    ids.discard(None)
    bindings={}
    if ids:
        for canonical in db.scalars(select(CanonicalType).where(CanonicalType.id.in_(ids))):
            for ref in (canonical.provenance or {}).get('universal_sources',[]):
                key=ref.get('source_key') or ''
                sha=ref.get('source_sha') or ''
                match=re.fullmatch(r'td1q2018:prd:([1-9][0-9]*)',key)
                if match and re.fullmatch(r'[a-f0-9]{64}',sha):
                    bindings.setdefault(canonical.id,set()).add((int(match[1]),sha))
    return bindings


def matches(row,products,bindings=None,*,source_modification_id=None,source_snapshot_sha=None,item_bindings=None):
    product_id=catalogue.row_product_id(row)
    if product_id is not None:
        product=products.get(product_id)
        # A source catalogue row has a hard modification + PRD identity.
        # A stale row from another modification must never inherit its OEM
        # merely because the two vehicles share the same PRD type number.
        source_bound=(getattr(row,'source',None)=='carpot.catalogue.v1')
        if source_bound and source_modification_id is not None:
            history = (item_bindings or {}).get(getattr(row, 'id', None))
            if history:
                active = history[-1] or {}
                current = (active.get('source_modification_id'), active.get('product_id'), active.get('snapshot_sha'))
                if current != (source_modification_id, product_id, source_snapshot_sha):
                    return None
            elif getattr(row,'catalog_key',None)!=f'car:{source_modification_id}:product:{product_id}':
                return None
        if eligible_product(product):
            return product
        # Unreviewed taxonomy does not erase a *proven exact source PRD link*.
        # Only the original row, pinned to this very same modification and
        # carrying article-linked evidence, can receive an OEM cross-reference.
        # This is NOT VIN/physical fitment and never enables lexical inference.
        if (source_bound and type(source_modification_id) is int
                and isinstance(product,dict) and product.get('kind')=='review'
                and type(product.get('article_count')) is int and product['article_count']>0):
            return product
        return None
    if bindings:
        canonical=(getattr(row,'plan_v3',None) or {}).get('canonical_part_type_id')
        linked=[products[pid] for pid,sha in bindings.get(canonical,())
                if pid in products and products[pid].get('source_prd_sha256')==sha
                and eligible_product(products[pid])]
        if linked:
            return linked[0] if len(linked)==1 else None
    if not row.name or not getattr(row,'category_name',None) or not getattr(row,'subcategory_name',None):
        return None
    identity=tuple(normalized(value) for value in (row.category_name,row.subcategory_name,row.name))
    matches=[]
    for product in products.values():
        path=product.get('category_path') or []
        if (product.get('kind') in ('part','consumable') and product.get('mapping_reviewed_by') and len(path)==3
                and tuple(normalized(value) for value in (*path[:2],product.get('name_uk')))==identity):
            matches.append(product)
    return matches[0] if len(matches)==1 else None


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
        result.append(dict(oem_number=n,supplier_id=o['supplier_id'],source_article=o['article_nr'],source_brand=o['brand'],
                           oem_source=o.get('oem_sources',{}).get(n,'catalogue_snapshot')))
    return result if len(result)<=1000 else []

def options(ref):
    if not isinstance(ref,dict):return []
    return list(dict.fromkeys(x['oem_number'] for x in ref.get('alternatives',[]) if isinstance(x,dict) and isinstance(x.get('oem_number'),str)))

def transferable_reference(ref):
    if not isinstance(ref, dict) or ref.get('source')!='carpot.catalogue':
        return False
    number=ref.get('oem_number')
    if not isinstance(number,str) or not number.strip() or len(number)>150:
        return False
    if number in options(ref):
        return True
    # Legacy explicit selections persisted the selected offer without alternatives.
    return (
        ref.get('status')=='user_selected_cross_reference'
        and 'alternatives' not in ref
        and all(type(ref.get(key)) is int and ref[key]>0 for key in
                ('source_modification_id','oem_manufacturer_id','product_id','supplier_id'))
        and all(isinstance(ref.get(key),str) and ref[key].strip() for key in
                ('source_article','source_brand'))
        and bool(re.fullmatch(r'[a-f0-9]{64}',ref.get('snapshot_sha') or ''))
    )

def automatic_identity(v):
    saved=(v.dismantling_v3 or {}).get(IDENTITY_KEY) or {}
    # Old first-by-year guesses remain in audit history but cannot drive new
    # automatic OEM. Existing explicitly pinned global_selection is separate.
    if saved.get('confirmation')=='auto_assumed':
        return None
    if saved.get('vehicle_basis')==basis(v) and saved.get('engine_variant')==normalized(v.engine_variant):
        return saved

def references(v):return (v.dismantling_v3 or {}).get(REF_KEY,{})

def eligible_row(row):
    return row.included and row.status!='absent' and not row.assembly_consumed_operation_id

def eligible_part(p):
    return not p.archived and p.quantity>0 and not p.reserved_quantity and p.availability!='absent' and not p.oem_number and not p.oem_provenance

def ref_for(v,row,payload,product,alternatives):
    return dict(**alternatives[0],source='carpot.catalogue',status='auto_selected_cross_reference',
        vin_verified=False,modification_selection=((v.dismantling_v3 or {}).get('global_selection') or automatic_identity(v) or {}).get('confirmation'),source_modification_id=payload['car_id'],oem_manufacturer_id=payload['manufacturer_id'],
        product_id=product['product_id'],snapshot_sha=payload['source_snapshot_sha'],observed_at=payload['observed_at'],retrieved_at=now().isoformat(),
        vehicle_basis=basis(v),engine_variant=normalized(v.engine_variant),row_identity=row_identity(row),alternatives=alternatives,selection_rule=RULE)

def physical_oem_confirmed(part):
    provenance = part.oem_provenance or {}
    return bool(part.oem_number and (
        provenance.get('physical_number_confirmed_by_user') is True
        or (provenance.get('source') == 'manual' and provenance.get('status') == 'user_confirmed')
    ))


def replaceable_stock(part,row):
    previous=part.oem_provenance or {}
    return (not part.archived and part.quantity>0 and not part.reserved_quantity
            and part.availability!='absent' and previous.get('source')=='carpot.catalogue'
            and not physical_oem_confirmed(part)
            and previous.get('status')==AUTO_STATUS and previous.get('plan_item_id')==row.id)


def refresh_stock_reference(db,v,row,part,ref):
    if ref and not valid_reference(v,row,ref):
        return False
    if not replaceable_stock(part,row):
        return bool(ref and fill_part(db,v,row,part,ref))
    previous=part.oem_provenance
    if not ref or valid_reference(v,row,previous):
        return False
    if part.article_number and (
        normalized(part.article_brand)!=normalized(ref.get('source_brand'))
        or normalized(part.article_number)!=normalized(ref.get('source_article'))
    ):
        return False
    before=snapshot(part)
    part.oem_number=ref['oem_number']
    part.oem_provenance={**ref,'plan_item_id':row.id,'physical_number_confirmed_by_user':False}
    record(db,v.account_id,part,'part_update','Оновлено каталожний OEM за модифікацією',before,after_extra={'automatic_oem':True})
    return True


def fill_part(db,v,row,part,ref,*,receipt=False):
    """Copy the reference only to a genuinely empty card; never overwrite a manual clear.
    If an article was set, require matching supplier+article evidence.
    """
    if not eligible_row(row) or not transferable_reference(ref) or not valid_reference(v,row,ref) or part.oem_number or part.oem_provenance or part.archived or part.reserved_quantity:return False
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
        self.plans={};self.offers={};self.exact={};self.oracle_refs={};self.oracle_cursors={};self.lock=threading.Lock();self.directory=None;self.directories={}
    def directory_candidates(self,v):
        """Rank source modifications by matching vehicle facts, then by source IDs."""
        code=lambda s:''.join(c for c in normalized(s) if c.isalnum())
        engine=code(v.engine_code)
        if type(v.year) is not int:return []
        maker=code(v.manufacturer)
        # "XC60 II (246)" is a TecDoc model/platform display label.
        # The platform code in parentheses is not part of the model identity.
        model=code(re.sub(r'[(][^)]*[)]','',v.model or ''))
        generation=code(v.generation) if normalized(v.generation) not in ('', 'не уточнено') else ''
        roman=('x','ix','viii','vii','vi','iv','iii','ii','v','i')
        aliases={'1':'i','2':'ii','3':'iii','4':'iv','5':'v','6':'vi','7':'vii','8':'viii','9':'ix','10':'x'}
        hint=generation
        if hint.startswith(model):hint=hint[len(model):]
        if hint.startswith('generation'):hint=hint[len('generation'):]
        if hint.startswith('gen'):hint=hint[3:]
        if hint in aliases:hint=aliases[hint]
        elif hint not in roman:
            hint=next((token for token in roman if hint.startswith(token) and
                       (hint[len(token):].startswith('20') or hint[len(token):].startswith('19'))),'')
        models={model}
        if hint:models.add(model+hint)
        # Query-side filtering must use the same aliases as the local matcher.
        # Unknown generation => fetch maker entries and match models locally.
        model_filter=models if generation and hint else None
        key=(maker,tuple(sorted(models)) if model_filter else ())
        entries=self.directory if self.directory is not None else self.directories.get(key)
        if entries is None:
            entries=[];cursor=0
            for _ in range(100):
                result=self.adapter.directory(after=cursor,maker_key=maker,model_keys=model_filter)
                entries.extend(result['items'])
                nxt=result.get('next_after')
                if nxt is None:break
                if type(nxt) is not int or nxt<=cursor:raise catalogue.CatalogueUnavailable('invalid_directory_cursor')
                cursor=nxt
            else:raise catalogue.CatalogueUnavailable('directory_limit')
            self.directories[key]=entries
        candidates=[]
        relaxed=[]
        # A VIN decoder can report "2" or "II (2017-)" while the source model
        # is called "XC60 II". Treat those as the same explicit generation.
        # Do not cross an explicitly different generation.
        for e in entries:
            entry_model=code(re.sub(r'[(][^)]*[)]','',e.get('model') or ''))
            suffix=entry_model[len(model):] if entry_model.startswith(model) else None
            source_generation=(suffix in roman or suffix in aliases)
            matches_model=(entry_model in models or
                (source_generation and (not generation or not hint or
                    aliases.get(suffix,suffix)==hint)))
            if code(e.get('manufacturer'))!=maker or not matches_model:continue
            attrs={a.get('attributetype'):str(a.get('displayvalue') or '') for a in e.get('specifications',[]) if isinstance(a,dict)}
            interval=attrs.get('ConstructionInterval') or e.get('modification',{}).get('constructioninterval') or ''
            years=[int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b',interval)]
            if not years or v.year<years[0] or (len(years)>1 and v.year>years[-1]):continue
            sha=e.get('snapshot_sha')
            ids=(e.get('source_modification_id'),e.get('model_id'),e.get('manufacturer_id'))
            if not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{64}',sha) or not all(type(n) is int and n>0 for n in ids):
                continue
            relaxed.append((*ids,sha,True))
            source_engine=code(attrs.get('EngineCode'))
            if engine and source_engine and source_engine!=engine:continue
            fuel=normalized(v.fuel_type);source_fuel=normalized(attrs.get('FuelType'))
            drive=normalized(v.drive_type);source_drive=normalized(attrs.get('DriveType'))
            fuel_groups=[{'petrol','gasoline','бензин','gas'},{'diesel','дизель','дизельное топливо'},{'hybrid','гібрид','гибрид'},{'electric','електро','электричество'}]
            drive_groups=[{'awd','4wd','full','повний','повний (awd)','привод на все колеса','all-wheel drive'},{'fwd','front','передній','передній (fwd)','передний привод','front-wheel drive'},{'rwd','rear','задній','задній (rwd)','задний привод','rear-wheel drive'}]
            if fuel and source_fuel and not (fuel==source_fuel or any(fuel in g and source_fuel in g for g in fuel_groups)):continue
            if drive and source_drive and not (drive==source_drive or any(drive in g and source_drive in g for g in drive_groups)):continue
            variant=code(v.engine_variant)
            description=code(e.get('modification',{}).get('description'))
            if variant and description and variant not in description:continue
            if v.engine_displacement_l is not None:
                capacity=re.fullmatch(r'([0-9]+(?:[.,][0-9]+)?)\s*l',attrs.get('Capacity','').strip(),re.I)
                if capacity and abs(float(capacity[1].replace(',','.'))-float(v.engine_displacement_l))>.05:continue
            sha=e.get('snapshot_sha')
            if not isinstance(sha,str) or not re.fullmatch(r'[a-f0-9]{64}',sha):continue
            ids=(e.get('source_modification_id'),e.get('model_id'),e.get('manufacturer_id'))
            if all(type(n) is int and n>0 for n in ids):
                evidence=(bool(engine and source_engine),sum(bool(x) for x in (
                    fuel and source_fuel,drive and source_drive,variant and description,attrs.get('Capacity') and v.engine_displacement_l,
                )))
                candidates.append(((-int(evidence[0]),-evidence[1],*ids),(*ids,sha,True)))
        # Internal staging observability: expose catalogue identity metadata only;
        # never log VIN, user identity, credentials or supplier articles.
        if is_staging() and maker=='volvo':
            log.info('OEM Volvo source candidates vehicle=%s requested_model=%s year=%s generation=%s remote_entries=%d source_models=%s evidence_matches=%d fallback_matches=%d',
                getattr(v,'id',None),model,v.year,generation,len(entries),
                sorted({code(e.get('model')) for e in entries})[:16],len(candidates),len(relaxed))
        # VIN identity must not degrade into "the first engine for this model
        # and year". This used to silently map B5 mild hybrids to T5 AWD and
        # diesel/unknown DAFs to an unrelated model when exact facts disagreed.
        # Only one uniquely best *evidence-backed* candidate can be automatic.
        # Unknown/tied engine versions remain registered without an OEM identity.
        ranked=sorted(candidates)
        if not ranked:return []
        best=ranked[0][0][:2]  # engine code evidence, then independent attributes
        top=[identity for score,identity in ranked if score[:2]==best]
        if best==(0,0) or len(set(top))!=1:return []
        return top

    def resolve_directory(self,v):
        options=self.directory_candidates(v)
        selected=next(iter(options),None)
        log.info('OEM modification lookup vehicle=%s alternatives=%d selected_source_id=%s',
                 getattr(v,'id',None),len(options),selected[0] if selected else None)
        return selected

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

    def get_offer_batch(self,payload,products):
        from app.api.unified_catalogue import saved_articles

        result={}
        ids=list(products)
        for start in range(0,len(ids),12):
            try:
                batch=self.adapter.article_batch(payload['car_id'],ids[start:start+12],payload['source_snapshot_sha'])
            except catalogue.CatalogueUnavailable:
                continue
            for pid,items in batch.items():
                try:
                    result[pid]=saved_articles(products[pid],{'payload':payload},
                        oem_manufacturer_id=payload['manufacturer_id'],linked_items=items)
                except (ValueError,TypeError,KeyError):
                    continue
                except Exception:
                    log.warning('Invalid OEM article batch for modification %s, product %s',payload['car_id'],pid)
        return result

    def sibling_candidates(self,payload,products):
        """Use exact PRD IDs from other snapshots of the identical source model."""
        if not products:
            return {}
        key=('siblings',payload['model_id'],payload['manufacturer_id'])
        if key not in self.directories:
            rows=[];cursor=0
            for _ in range(100):
                page=self.adapter.directory(after=cursor,model_id=payload['model_id'])
                rows.extend(page['items'])
                nxt=page.get('next_after')
                if nxt is None:
                    break
                if type(nxt) is not int or nxt<=cursor:
                    raise catalogue.CatalogueUnavailable('invalid_directory_cursor')
                cursor=nxt
            else:
                raise catalogue.CatalogueUnavailable('directory_limit')
            self.directories[key]=rows
        result={pid:[] for pid in products}
        for entry in self.directories[key]:
            car=entry.get('source_modification_id')
            if (car==payload['car_id'] or entry.get('model_id')!=payload['model_id']
                    or entry.get('manufacturer_id')!=payload['manufacturer_id']):
                continue
            try:
                other=self.plan((car,payload['model_id'],payload['manufacturer_id'],entry['snapshot_sha'],True))
                eligible={p['product_id']:p for p in other['categories']
                          if p['product_id'] in products and eligible_product(p) and p['article_count']>0}
                offers=self.get_offer_batch(other,eligible)
            except (catalogue.CatalogueUnavailable,KeyError,ValueError):
                continue
            for pid,items in offers.items():
                result[pid].extend((car,eligible[pid],item) for item in items)
        return result

    def oracle_numbers(self, manufacturer_id, supplier_id, article_number):
        """Exact manufacturer/supplier/article cross references, never VIN fitment.

        Cache successful empty results as well; transient failures are retried on
        future sweeps. No call can reach Oracle except via CatalogueAdapter.
        """
        if (not oracle_enabled() or type(manufacturer_id) is not int or manufacturer_id<1
                or type(supplier_id) is not int or not 1<=supplier_id<=65535
                or not isinstance(article_number,str) or not 1<=len(article_number)<=64):
            return None
        key=(manufacturer_id,supplier_id,article_number)
        with self.lock:
            if key in self.oracle_refs:return self.oracle_refs[key]
        try:
            numbers=self.adapter.oracle_oem_by_article(supplier_id,article_number,manufacturer_id)
        except (catalogue.CatalogueUnavailable,AttributeError):
            return None
        if (not isinstance(numbers,list) or len(numbers)>50
                or any(not isinstance(n,str) or not 1<=len(n)<=64 for n in numbers)):
            return None
        numbers=sorted(set(numbers))
        with self.lock:
            if len(self.oracle_refs)>=4096:self.oracle_refs.clear()
            self.oracle_refs[key]=numbers
        return numbers

    def enrich_oracle_offers(self,payload,data,priority=None):
        """Fill missing OEMs only on already modification-linked catalogue articles.

        One candidate per PRD type first, then other supplier articles.
        The rotating cursor prevents the fixed per-pass budget from starving
        later parts, including when earlier source articles have no OEM.
        """
        if not oracle_enabled() or not isinstance(data,dict):return data
        manufacturer_id=payload.get('manufacturer_id')
        if type(manufacturer_id) is not int or manufacturer_id<1:return data
        priority=priority or {}
        rounds={}
        for pid,offers in data.items():
            if not isinstance(offers,list) or any(
                    isinstance(o,dict) and o.get('oem_numbers') for o in offers):
                continue
            ordered=[o for o in offers if (
                isinstance(o,dict) and isinstance(o.get('brand'),str) and o['brand']
                and type(o.get('supplier_id')) is int
                and isinstance(o.get('article_nr'),str) and o['article_nr']
            )]
            preferred=priority.get(pid)
            if preferred:
                ordered.sort(key=lambda o: (
                    normalized(o['brand'])!=preferred[0] or
                    normalized(o['article_nr'])!=preferred[1],
                    o['supplier_id'],o['article_nr']))
            rounds[pid]=ordered
        candidates=[]
        for index in range(20):
            for pid in sorted(rounds, key=lambda p:(p not in priority,p)):
                if index<len(rounds[pid]):
                    candidates.append((pid,rounds[pid][index]))
        if not candidates:return data
        cursor_key=(payload.get('car_id'),payload.get('source_snapshot_sha'))
        with self.lock:
            offset=self.oracle_cursors.get(cursor_key,0)%len(candidates)
        rotated=candidates[offset:]+candidates[:offset]
        attempts=0;failures=0
        for pid,offer in rotated:
            if attempts>=ORACLE_LOOKUP_LIMIT or failures>=2:break
            if any(isinstance(o,dict) and o.get('oem_numbers') for o in data[pid]):
                continue
            attempts+=1
            numbers=self.oracle_numbers(manufacturer_id,offer['supplier_id'],offer['article_nr'])
            if numbers is None:
                failures+=1
            elif numbers:
                offer['oem_numbers']=numbers
                sources=dict(offer.get('oem_sources') or {})
                sources.update({n:'oracle_gateway_cross_reference' for n in numbers})
                offer['oem_sources']=sources
        with self.lock:
            if len(self.oracle_cursors)>=2048:self.oracle_cursors.clear()
            self.oracle_cursors[cursor_key]=(offset+attempts)%len(candidates)
        return data

    def exact_lookup(self,make,brand,article,supplier_id,manufacturer_id=None):
        key=(make,brand,article,supplier_id,manufacturer_id)
        with self.lock:
            if key in self.exact:return self.exact[key]
        result=None
        try:
            result=self.adapter.exact_oem(make,brand,article,supplier_id)
        except catalogue.CatalogueUnavailable:
            # Older Volvo pilot contract, only with a known exact supplier ID.
            if normalized(make)=='volvo' and supplier_id:
                try:
                    candidate=self.adapter.article(supplier_id,article,brand)
                    if not candidate.get('truncated'):
                        result={**candidate,'manufacturer':make,'manufacturer_id':120,'supplier_id':supplier_id,
                                'supplier_name':brand,'article_number':article}
                except catalogue.CatalogueUnavailable:
                    pass
        # A verified legacy exact-article response can also supply the maker ID
        # when the donor has no pinned modification yet. Never guess the ID by name.
        resolved_make_id=manufacturer_id
        old_make_id=(result or {}).get('manufacturer_id')
        if (resolved_make_id is None and type(old_make_id) is int and old_make_id>0
                and normalized((result or {}).get('manufacturer'))==normalized(make)):
            resolved_make_id=old_make_id
        if (supplier_id and not (result or {}).get('oem_numbers')
                and type(resolved_make_id) is int and resolved_make_id>0):
            if old_make_id is None or old_make_id==resolved_make_id:
                numbers=self.oracle_numbers(resolved_make_id,supplier_id,article)
                if numbers:
                    result=dict(manufacturer=make,manufacturer_id=resolved_make_id,
                        supplier_id=supplier_id,supplier_name=brand,
                        article_number=article,oem_numbers=numbers,
                        oem_source='oracle_gateway_cross_reference')
        if result is not None:
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
    alternatives=[dict(oem_number=n,supplier_id=result['supplier_id'],source_article=result['article_number'],source_brand=result['supplier_name'],**({'oem_source':result['oem_source']} if result.get('oem_source') else {})) for n in numbers]
    before=snapshot(part);part.oem_number=numbers[0]
    part.oem_provenance=dict(**alternatives[0],source='carpot.catalogue',status='auto_selected_cross_reference',
        vin_verified=False,oem_manufacturer_id=result['manufacturer_id'],vehicle_basis=basis(v),
        retrieved_at=now().isoformat(),
        alternatives=alternatives,selection_rule='exact_supplier_article_lexical')
    record(db,v.account_id,part,'part_update','Каталожний OEM',before,after_extra={'automatic_oem':True})
    return True

def accepts_automatic_plan(v):
    state = v.dismantling_v3 or {}
    return not (set(state) - {'global_selection', IDENTITY_KEY, CANDIDATES_KEY, OUTCOMES_KEY}) and not v.ktype


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
        bindings=canonical_prd_bindings(db,rows)
        old_refs=references(v)
        item_bindings = (v.dismantling_v3 or {}).get(plan_item_binding.KEY, {})
        selection_revision = (v.dismantling_v3 or {}).get('catalogue_selection_revision', 0)
        linked={p.id:p for p in db.scalars(select(Part).where(Part.vehicle_id==v.id,Part.account_id==account_id))}
        exact={p.id:k for p in linked.values() if (k:=exact_key(p,v))}
        needs=[]
        for row in rows:
            if not eligible_row(row):
                continue
            ref=old_refs.get(row.id)
            part=linked.get(row.part_id)
            if (not valid_reference(v,row,ref) or not options(ref) or part and (
                    eligible_part(part) or replaceable_stock(part,row) and not valid_reference(v,row,part.oem_provenance)
            )):
                needs.append(row)
        can_copy=any(r.part_id in linked and eligible_part(linked[r.part_id])
                     and transferable_reference(old_refs.get(r.id)) for r in needs)
        saved_identity=automatic_identity(v)
        has_selection=(v.dismantling_v3 or {}).get('global_selection') or catalogue.saved_state(v)
        discover=not has_selection and not saved_identity
        if saved_identity and not identity and not has_selection:
            identity=tuple(saved_identity[k] for k in ('car_id','model_id','manufacturer_id','snapshot_sha','global_source'))
        create_plan = accepts_automatic_plan(v) and not rows and not linked and not catalogue.has_plan_history(db, v)
        if not exact and not needs and not discover and not create_plan:return 0
    assumed=None
    if discover:
        try:assumed=cache.resolve_directory(v)
        except catalogue.CatalogueUnavailable:pass
        identity=assumed or identity
    publish_identity=discover and identity is not None
    type_rows=needs
    payload=None;products={};data={};exact_data={};siblings={}
    if identity and (type_rows or publish_identity or create_plan):
        try:
            payload=cache.plan(identity);products={p['product_id']:p for p in payload['categories']}
            needed = {
                pid: product for pid, product in products.items()
                if create_plan and eligible_product(product) and product['article_count']>0
            }
            for row in type_rows:
                p=matches(row,products,bindings,source_modification_id=payload['car_id'],
                    source_snapshot_sha=payload['source_snapshot_sha'],item_bindings=item_bindings)
                if p:needed[p['product_id']]=p
            def offers_for(product):
                try:return cache.get_offers(payload,product)
                except Exception:return None
            data=cache.get_offer_batch(payload,needed)
            remaining={pid:p for pid,p in needed.items() if pid not in data}
            with ThreadPoolExecutor(max_workers=4) as pool:
                data.update({pid:offers for pid,offers in zip(remaining,pool.map(offers_for,remaining.values())) if offers is not None})
            focus={}
            for row in type_rows:
                product=matches(row,products,bindings,source_modification_id=payload['car_id'],
                    source_snapshot_sha=payload['source_snapshot_sha'],item_bindings=item_bindings)
                part=linked.get(row.part_id)
                if product and part and part.article_number and part.article_brand:
                    focus[product['product_id']]=(normalized(part.article_brand),normalized(part.article_number))
            cache.enrich_oracle_offers(payload,data,priority=focus)
            try:
                possible={pid for pid,offers in data.items() if not choices(offers,product=products[pid])}
                possible.update(
                    product['product_id'] for row in type_rows
                    if (product:=matches(row,products,bindings,source_modification_id=payload['car_id'],
                    source_snapshot_sha=payload['source_snapshot_sha'],item_bindings=item_bindings))
                    and product['product_id'] in data
                    and not choices(data[product['product_id']],linked.get(row.part_id),row,product)
                )
                siblings=cache.sibling_candidates(payload,possible)
            except catalogue.CatalogueUnavailable:
                pass
        except Exception:
            # Exact-article lookup remains independent of snapshot availability.
            log.warning('OEM snapshot lookup deferred for donor %s',vehicle_id)
            payload=None;products={};data={}
    if exact:
        unique=list(set(exact.values()))
        with ThreadPoolExecutor(max_workers=4) as pool:
            make_id=identity[2] if identity and type(identity[2]) is int else None
            exact_data=dict(zip(unique,pool.map(lambda k:cache.exact_lookup(*k,manufacturer_id=make_id),unique)))
    if not payload and not can_copy and not any(exact_data.values()):return 0
    with Session(engine) as db:
        db.execute(text("SET LOCAL lock_timeout = '2s'"))
        # PostgreSQL key_share=True alone emits FOR NO KEY UPDATE (exclusive).
        # read=True is required for the intended nonexclusive FOR KEY SHARE.
        db.scalar(select(Account).where(Account.id==account_id).with_for_update(read=True,key_share=True))
        v=db.scalar(select(Vehicle).where(Vehicle.id==vehicle_id,Vehicle.account_id==account_id,Vehicle.archived.is_(False)).with_for_update())
        if not v or basis(v)!=old_basis or normalized(v.engine_variant)!=old_variant or source_identity(v)!=direct_identity:return 0
        if (v.dismantling_v3 or {}).get('catalogue_selection_revision', 0) != selection_revision:
            return 0
        rows=list(db.scalars(select(DismantlingItem).where(DismantlingItem.vehicle_id==v.id,DismantlingItem.account_id==account_id).order_by(DismantlingItem.id).with_for_update()))
        parts={p.id:p for p in db.scalars(select(Part).where(Part.vehicle_id==v.id,Part.account_id==account_id).order_by(Part.id).with_for_update())}
        if (payload and create_plan and accepts_automatic_plan(v) and not rows and not parts
                and any(eligible_product(product) for product in products.values())
                and not catalogue.has_plan_history(db, v)):
            catalogue.persist(db, v, {'payload':payload, 'sha256':digest(payload)}, allow_partial=True)
            rows = list(db.scalars(select(DismantlingItem).where(
                DismantlingItem.account_id==account_id, DismantlingItem.vehicle_id==v.id
            ).order_by(DismantlingItem.id)))
        refs=dict(references(v));added=0;changed=False;stock_changes=0
        before=snapshot(v)
        state=dict(v.dismantling_v3 or {})
        if payload and publish_identity and not state.get('global_selection'):
            state[IDENTITY_KEY]=dict(car_id=payload['car_id'],model_id=payload['model_id'],
                manufacturer_id=payload['manufacturer_id'],snapshot_sha=payload['source_snapshot_sha'],
                global_source=identity[4],modification_description=payload['modification'].get('description'),
                vehicle_basis=old_basis,engine_variant=old_variant,
                # A new automatic identity requires uniquely best technical
                # evidence; it is still NOT VIN-verified exact factory fitment.
                confirmation='catalogue_evidence',vin_verified=False)
            changed=True
        if changed:
            v.dismantling_v3=state
        sold=set(db.scalars(select(Operation.part_id).where(
            Operation.account_id==account_id,Operation.part_id.in_(parts),Operation.type=='sale'
        ))) if parts else set()
        item_bindings = dict(state.get(plan_item_binding.KEY, {}))
        candidates=dict(state.get(CANDIDATES_KEY) or {})
        outcomes=dict(state.get(OUTCOMES_KEY) or {})
        for row in rows:
            if not eligible_row(row) or (row.part_id in sold and row.id not in item_bindings):
                continue
            part=parts.get(row.part_id)
            ref=refs.get(row.id)
            product=matches(row,products,bindings,source_modification_id=payload['car_id'],
                    source_snapshot_sha=payload['source_snapshot_sha'],item_bindings=item_bindings) if payload else None
            pid=product['product_id'] if product else None
            evaluated=payload is not None and (
                pid in data or pid is None and (catalogue.row_product_id(row) is not None or
                    ref and ref.get('status')==AUTO_STATUS and not valid_reference(v,row,ref))
            )
            if evaluated:
                alternatives=choices(data.get(pid,[]),None if row.id in item_bindings else part,row,product)
                valid=valid_reference(v,row,ref)
                if (not valid or not options(ref)) and alternatives:
                    if valid or (row.id not in item_bindings and part and (part.oem_number or part.oem_provenance) and not replaceable_stock(part,row)):
                        chosen=ref['oem_number'] if valid else part.oem_number
                        match=next((a for a in alternatives if a['oem_number']==chosen),None)
                        alternatives=[match,*[a for a in alternatives if a!=match]] if match else []
                    if alternatives:
                        if valid:
                            ref={**ref,'alternatives':alternatives}
                        else:
                            ref=ref_for(v,row,payload,product,alternatives)
                        refs[row.id]=ref;added+=1;changed=True
                if ref and not valid_reference(v,row,ref) and ref.get('status')==AUTO_STATUS:
                    refs.pop(row.id)
                    ref=None;changed=True
                other=[]
                if not ref and pid in siblings:
                    for car,other_product,offer in siblings[pid]:
                        other.extend(dict(**item,source_modification_id=car,status='unconfirmed')
                                     for item in choices([offer],part,row,other_product))
                    other=list({(item['source_modification_id'],item['oem_number']):item for item in other}.values())[:100]
                if other != candidates.get(row.id,[]):
                    if other:
                        candidates[row.id]=other
                    else:
                        candidates.pop(row.id,None)
                    changed=True
            if payload is not None and not valid_reference(v,row,ref):
                outcome=('no_verified_prd_binding' if pid is None else
                         'no_selected_modification_oem' if pid in data else 'article_lookup_pending')
                if outcomes.get(row.id)!=outcome:
                    outcomes[row.id]=outcome;changed=True
            elif valid_reference(v,row,ref) and row.id in outcomes:
                outcomes.pop(row.id);changed=True
            if pid in data and row.id in item_bindings:
                changed |= plan_item_binding.record_evidence(
                    item_bindings, row.id, data[pid], ref if valid_reference(v,row,ref) else None)
            if part and row.part_id not in sold and (ref or evaluated) and refresh_stock_reference(db,v,row,part,ref):
                stock_changes+=1
        for pid,key in exact.items():
            part=parts.get(pid);result=exact_data.get(key)
            if part and pid not in sold and result and exact_key(part,v)==key and fill_exact(db,v,part,result):stock_changes+=1
        if changed:
            if item_bindings:
                state[plan_item_binding.KEY] = item_bindings
            v.dismantling_v3={**state,REF_KEY:refs,CANDIDATES_KEY:candidates,OUTCOMES_KEY:outcomes}
            record(db,account_id,v,'vehicle_update','Каталожні OEM',before,after_extra={'automatic_oem':True})
        db.commit()
        # A populated legacy stock field is not evidence of current fitment.
        active=[p for p in parts.values() if not p.archived and p.quantity>0 and p.availability!='absent']
        valid_refs=sum(bool(eligible_row(row) and valid_reference(v,row,refs.get(row.id))
                            and transferable_reference(refs.get(row.id))) for row in rows)
        failures={name:sum(value==name for value in outcomes.values())
                  for name in ('no_verified_prd_binding','no_selected_modification_oem','article_lookup_pending')}
        log.info('OEM lifecycle coverage vehicle=%s donor_number=%s model=%s year=%s source_modification=%s plan_total=%d plan_valid_oem=%d stock_total=%d stock_nonempty_oem=%d unmatched_source_prd=%d missing_selected_oem=%d pending_articles=%d',
                 vehicle_id,v.number,v.model,v.year,payload['car_id'] if payload else None,
                 sum(eligible_row(row) for row in rows),valid_refs,
                 len(active),sum(bool(p.oem_number) for p in active),
                 failures['no_verified_prd_binding'],failures['no_selected_modification_oem'],
                 failures['article_lookup_pending'])
        log.info('OEM enrichment committed vehicle=%s plan_refs=%d stock_updates=%d source_modification=%s',
                 vehicle_id,added,stock_changes,payload['car_id'] if payload else None)
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
