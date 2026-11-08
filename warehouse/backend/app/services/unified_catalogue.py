"""Read-only server adapter and cost-safe resolver. Never touches stock or provider billing."""
import hashlib
import json
import os
import time
from urllib.parse import urlsplit

import httpx


class CatalogueUnavailable(Exception):
    pass


class CatalogueAdapter:
    def __init__(self, *, transport=None):
        self.transport = transport

    def get(self, path, params=None):
        origin = os.getenv('WAREHOUSE_CATALOGUE_URL', '')
        key = os.getenv('WAREHOUSE_CATALOGUE_KEY', '')
        allowed = os.getenv('WAREHOUSE_CATALOGUE_HOST', '')
        url = urlsplit(origin)
        # Exact single admin-configured HTTPS host; no credentials/paths/redirects.
        if not key or not allowed or url.scheme != 'https' or url.hostname != allowed or url.netloc != allowed or url.path not in ('', '/') or url.query or url.fragment:
            raise CatalogueUnavailable('not_configured')
        started=time.monotonic()
        try:
            with httpx.Client(transport=self.transport, timeout=httpx.Timeout(5, connect=2), follow_redirects=False, trust_env=False) as client:
                with client.stream('GET', origin.rstrip('/') + '/api/v1/volvo/' + path,
                                   params=params, headers={'X-Catalogue-Key': key}) as response:
                    if response.status_code != 200:
                        raise CatalogueUnavailable('unavailable')
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic()-started>5:raise CatalogueUnavailable('deadline_exceeded')
                        body.extend(chunk)
                        if len(body) > 8 * 1024 * 1024:
                            raise CatalogueUnavailable('response_too_large')
                    return json.loads(body)
        except (httpx.HTTPError, ValueError):
            raise CatalogueUnavailable('unavailable') from None

    def article(self, supplier_id, article_number, manufacturer):
        result=self.get('article',{'supplier_id':supplier_id,'article_number':article_number})
        import unicodedata
        normalize=lambda v:unicodedata.normalize('NFKC',v if isinstance(v,str) else '').strip().casefold()
        if not isinstance(result,dict) or result.get('supplier_id')!=supplier_id or result.get('article_number')!=article_number or not normalize(manufacturer) or normalize(result.get('supplier_name'))!=normalize(manufacturer):
            raise CatalogueUnavailable('supplier_identity_unverified')
        # Cross-reference evidence only. A matching article never proves VIN fitment.
        return dict(source='carpot-catalogue',oem_numbers=result.get('oem_numbers',[]),
            truncated=bool(result.get('oem_numbers_truncated')),observed_at=result.get('observed_at'),
            fitment='cross_reference_only',vin_verified=False,photo=None)

    def modifications(self, model_id):
        result = self.get('modifications', {'model_id': model_id})
        if not isinstance(result, dict) or not isinstance(result.get('items'), list) or len(result['items'])>100:
            raise CatalogueUnavailable('invalid_contract')
        for item in result['items']:
            if not isinstance(item,dict) or item.get('model_id') != model_id or type(item.get('source_modification_id')) is not int:
                raise CatalogueUnavailable('invalid_identity')
        return result

    def plan(self, source_modification_id):
        data = self.get(f'modifications/{int(source_modification_id)}/plan')
        try:
            payload = data['payload']
            actual = hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if actual!=data['sha256'] or payload['car_id']!=source_modification_id or payload['manufacturer_id']!=120:
                raise ValueError()
            validate_plan(payload)
        except (ValueError,KeyError,TypeError,AttributeError):
            raise CatalogueUnavailable('invalid_contract') from None
        return data

    def articles(self, car_id, product_id, snapshot_sha):
        data=self.get(f'modifications/{int(car_id)}/articles',{'product_id':product_id,'snapshot_sha':snapshot_sha})
        if not isinstance(data,dict) or data.get('snapshot_sha')!=snapshot_sha or data.get('car_id')!=car_id or data.get('product_id')!=product_id or not isinstance(data.get('items'),list):
            raise CatalogueUnavailable('pinned_snapshot_mismatch')
        items=data['items']
        seen=set()
        for item in items:
            if not isinstance(item,dict) or type(item.get('supplier_id')) is not int or item.get('car_id')!=car_id or not isinstance(item.get('article_number'),str):
                raise CatalogueUnavailable('article_identity_mismatch')
            identity=(item['supplier_id'],item['article_number'])
            if identity in seen:raise CatalogueUnavailable('duplicate_article_identity')
            seen.add(identity)
        return items


class CatalogueResolver:
    """No implicit paid network path: paid is a proposal routed to the existing UI."""
    def __init__(self, adapter=None):
        self.adapter = adapter or CatalogueAdapter()

    def resolve(self, *, make, source_modification_id=None, saved_plan_parts=False):
        reason = 'missing_exact_modification'
        if make.casefold().strip() == 'volvo' and source_modification_id:
            try:
                envelope = self.adapter.plan(source_modification_id)
                payload = envelope['payload']
                categories = payload['categories']
                if payload['coverage'] == 'complete_verified' and payload.get('coverage_verified') is True and payload.get('taxonomy_status')=='reviewed' and categories and all(
                    r.get('name_uk') and len(r.get('category_path', [])) == 3 and r.get('mapping_reviewed_by') and r.get('kind') in ('part','consumable','equipment') for r in categories
                ):
                    return dict(source='catalogue', cost='free', coverage='complete_verified', plan=envelope, reason=None)
                reason = 'taxonomy_unreviewed' if payload.get('coverage_verified') is True and payload.get('taxonomy_status')!='reviewed' else 'partial_coverage'
            except (CatalogueUnavailable, KeyError, TypeError):
                reason = 'catalogue_unavailable'
        return dict(source='saved_plan_parts' if saved_plan_parts else 'base', cost='free',
            coverage='saved' if saved_plan_parts else 'generic', reason=reason, plan=None,
            paid_lookup='explicit_existing_confirmation_only')


def vehicle_basis(vehicle):
    return {key:getattr(vehicle,key) for key in ('manufacturer','model','year','engine','fuel_type','transmission','ktype')}


def needs_review(vehicle):
    state=saved_state(vehicle)
    return bool(state and state.get('vehicle_basis')!=vehicle_basis(vehicle))


def saved_state(vehicle):
    return (vehicle.dismantling_v3 or {}).get('unified_catalogue')


def persist(db, who, vehicle, envelope):
    """Persist potential types only. Existing plan/manual data never overwritten."""
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models import DismantlingItem
    from app.services.inventory import record, snapshot
    existing = saved_state(vehicle)
    if existing:
        if existing['payload'].get('source_snapshot_sha',existing['sha256']) != envelope['payload'].get('source_snapshot_sha',envelope['sha256']):
            raise HTTPException(409, 'Збережений план вже існує. Зміна модифікації потребує окремого узгодження.')
        return existing
    # Never merge a new source into a donor with work/history by similar labels.
    from app.models import Part, VehicleChecklistItem
    for cls in (DismantlingItem, Part, VehicleChecklistItem):
        if db.scalar(select(cls.id).where(cls.account_id == who.workspace_account_id, cls.vehicle_id == vehicle.id).limit(1)):
            raise HTTPException(409, 'Автомобіль вже має план або складську історію. Наявні рішення збережено.')
    payload = envelope['payload']
    validate_plan(payload)
    before = snapshot(vehicle)
    for row in payload['categories']:
        root, sub, _ = row['category_path']
        stable = lambda text: hashlib.sha256(text.encode()).hexdigest()[:24]
        db.add(DismantlingItem(account_id=who.workspace_account_id, vehicle_id=vehicle.id,
            source='carpot.catalogue.v1', catalog_key=f"car:{payload['car_id']}:product:{row['product_id']}",
            category_key=stable(root), category_name=root, subcategory_key=stable(root + '/' + sub),
            subcategory_name=sub, name=row['name_uk'], position='', quantity=1))
    projection=compact_payload(payload)
    local_sha=hashlib.sha256(json.dumps(projection,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    envelope={'payload':projection,'sha256':local_sha,'vehicle_basis':vehicle_basis(vehicle)}
    vehicle.dismantling_v3 = {**(vehicle.dismantling_v3 or {}), 'unified_catalogue': envelope}
    record(db, who.workspace_account_id, vehicle, 'unified_catalogue_save',
           'Збережено потенційний план Catalogue; склад не змінено', before)
    db.flush()
    return envelope


def workspace_entries(db, who, vehicle):
    from sqlalchemy import select
    from app.models import DismantlingItem, Part
    state = saved_state(vehicle)
    if not state:
        return []
    payload = state['payload']
    products = {r['product_id']: r for r in payload['categories']}
    parts = {p.id: p for p in db.scalars(select(Part).where(Part.account_id == who.workspace_account_id, Part.vehicle_id == vehicle.id))}
    result = []
    for r in db.scalars(select(DismantlingItem).where(DismantlingItem.account_id == who.workspace_account_id,
        DismantlingItem.vehicle_id == vehicle.id, DismantlingItem.source == 'carpot.catalogue.v1')):
        prefix = f"car:{payload['car_id']}:product:"
        if not r.catalog_key.startswith(prefix):
            continue
        product = products.get(int(r.catalog_key[len(prefix):]))
        if product is None:
            continue
        ps = [parts[r.part_id]] if r.part_id in parts else []
        result.append(dict(key='catalogue:' + r.id, original=str(product.get('name_source') or r.name),
            manual_name=r.name, category=r.category_name, position=r.position, kind=product.get('kind','part' if payload.get('schema')=='carpot.volvo.v1' else 'review'), pt_id=None,
            parts=ps, receipt=None, included=r.included,
            base_state='dismantled' if r.status == 'dismantled' else 'planned'))
    return result


PLAN_KEYS=('schema','manufacturer_id','car_id','model_id','modification','observed_at','source_snapshot_sha','coverage','coverage_verified','taxonomy_status','photos')
TYPE_KEYS=('product_id','name_source','name_uk','category_path','kind','mapping_reviewed_by','taxonomy_note','article_count')


def compact_payload(payload):
    result={k:payload[k] for k in PLAN_KEYS if k in payload}
    result['categories']=[{k:r[k] for k in TYPE_KEYS if k in r} for r in payload['categories']]
    return result


def validate_plan(payload):
    import re
    from datetime import datetime
    from app.services.catalogue_carpot_sections import SECTIONS, SUBCATEGORIES
    datetime.fromisoformat(payload['observed_at'].replace('Z','+00:00'))
    if payload.get('schema')!='carpot.volvo.plan.v2' or not re.fullmatch('[0-9a-f]{64}',payload.get('source_snapshot_sha','')):
        raise ValueError('Compact pinned plan required')
    if type(payload['model_id']) is not int or payload['model_id']<=0 or type(payload['car_id']) is not int or payload['car_id']<=0:raise ValueError()
    if payload.get('coverage') not in ('partial','complete_verified'):raise ValueError()
    rows=payload['categories']
    if not isinstance(rows,list) or not 0<=len(rows)<=10000:raise ValueError()
    if len(json.dumps(compact_payload(payload),ensure_ascii=False).encode())>512*1024:raise ValueError('Compact plan exceeds 512 KiB')
    seen=set()
    for row in rows:
        product=row['product_id']
        if type(product) is not int or product<=0 or product in seen:raise ValueError()
        seen.add(product)
        if row.get('kind') not in ('part','consumable','equipment','review'):raise ValueError()
        if payload.get('taxonomy_status')=='reviewed':
            path=row['category_path']
            if len(path)!=3 or path[0] not in SECTIONS or any(not isinstance(p,str) or not 1<=len(p)<=100 for p in path) or not isinstance(row['name_uk'],str) or not 1<=len(row['name_uk'])<=200 or not row.get('mapping_reviewed_by'):raise ValueError()
            if path[1] not in {label for label,_ in SUBCATEGORIES[SECTIONS.index(path[0])]}:raise ValueError('Unknown corporate subsection')
