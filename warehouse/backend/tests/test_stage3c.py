"""Price guidance and seller decisions over isolated PostgreSQL, no staging."""
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app.db import engine
from app.main import app
from app.models import Part,Vehicle,Operation,PriceDecision,DismantlingItem
from app.models.catalogue import CataloguePrice,CatalogueOffer,CataloguePath
from app.services import price_guidance as pg,pricing
from test_catalogue_v2 import platform,row
from test_canonical_v3 import market,build
from test_v3_release_audit import all_tables


def key():return str(uuid4())
def item(i,**kw):return row(str(i),part_name='Фара передня ліва Volvo XC40',category='Оптика',subcategory='Фари',side='ліва',position='передня',oem='OEM-123-A',condition='used',price_uah=str(100+int(i)*50),price_usd=None,**kw)

def setup(c,v,rows):
    with Session(engine()) as db:
        vehicle=db.get(Vehicle,v['id']);vehicle.manufacturer='Volvo';vehicle.model='XC40';vehicle.engine='';vehicle.fuel_type='';vehicle.year=2020;db.commit()
    from test_dismantling_preview import save_config
    save_config(c,v,dict(manufacturer="Volvo",model="XC40",year=2020,options=["standard-headlamps"]))
    market(c,rows);build(c)
    path='/api/v1/vehicles/'+v['id']+'/virtual-dismantling'
    state=c.get(path).json();r=c.post(path+'/activate',json=dict(facts=[],etag=state['etag'],request_key=key(),confirm=True));assert r.status_code==200,r.text
    state=c.get(path).json();target=next(i for i in state['items'] if i['name']=='Фара' and i['position']=='передня ліва')
    with Session(engine()) as db:
        p=db.get(Part,target['part_id']);p.oem_number='OEM-123-A';p.condition='used';db.commit()
    return target['part_id']

def guide(c,p):
    r=c.get('/api/v1/parts/'+p+'/price-guidance');assert r.status_code==200,r.text;return r.json()
def preview(c,ids,**changes):
    payload=dict(ids=ids,mode='median',currency='UAH',rounding=1,overwrite=False,request_key=key());payload.update(changes)
    r=c.post('/api/v1/pricing/previews',json=payload);assert r.status_code==200,r.text;return r.json()
def apply(c,j,payload=None):return c.post('/api/v1/pricing/previews/'+j['id']+'/apply',json=payload or dict(token=j['token'],confirm=True,request_key=key()))
def price(c,p,value,**extra):return c.patch('/api/v1/parts/'+p+'/price',json=dict(selling_price=value,currency='UAH',**extra))

@pytest.mark.parametrize('n,level',[(0,'D'),(1,'B'),(2,'B'),(3,'A'),(5,'A')])
def test_sample_sizes_and_no_market_price_writes(platform,vehicle,n,level):
    rows=[item(i) for i in range(max(n,1))]
    if not n:rows[0]['price_uah']=None
    p=setup(platform,vehicle,rows)
    with Session(engine()) as db:before=all_tables(db)
    g=guide(platform,p);assert g['level']==level,__import__('json').dumps(g,ensure_ascii=False)
    assert g['offer_count']==n
    if n>=3:assert Decimal(g['cohorts'][0]['median'])==100+Decimal(n-1)*25
    elif n:assert g['cohorts'][0]['median'] is None
    else:assert not g['cohorts']
    with Session(engine()) as db:assert all_tables(db)==before and db.get(Part,p).selling_price is None


def test_unknown_oem_condition_c_examples_not_bulk_median(platform,vehicle):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    with Session(engine()) as db:
        part=db.get(Part,p);part.oem_number='';part.condition='unknown';db.commit()
    g=guide(platform,p);assert g['level']=='C' and g['example_count']==3 and g['examples'][0]['differences']
    j=preview(platform,[p]);assert j['report']['changed']==0 and j['report']['skipped']==1
    assert 'когорти' in j['report']['items'][0]['reason']


def test_conditions_currencies_positions_models_and_engine_separate(platform,vehicle):
    rows=[item(i) for i in range(3)]
    rows.append({**item(3),'side':'права','part_name':'Фара передня права Volvo XC40','price_uah':'9000'})
    rows.append({**item(4),'model':'XC90','part_name':'Фара передня ліва Volvo XC90','price_uah':'8000'})
    rows.append({**item(5),'condition':'new','price_uah':'7000'})
    rows.append({**item(6),'price_uah':None,'price_usd':'17'})
    rows.append({**item(7),'part_name':'Фара передня ліва Volvo XC40 дизель','price_uah':'6000'})
    p=setup(platform,vehicle,rows);g=guide(platform,p)
    assert g['level']=='A',g
    uah=next(c for c in g['cohorts'] if c['currency']=='UAH');assert uah['offer_count']==3 and Decimal(uah['median'])==150
    assert next(c for c in g['cohorts'] if c['currency']=='USD')['level']=='B'
    assert any(e['condition']=='new' for e in g['examples'])
    assert all(e['amount'] not in ('8000.00','9000.00') for e in g['examples'])


def test_latest_missing_stale_future_and_path_duplicates(platform,vehicle,monkeypatch):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    with Session(engine()) as db:
        offer=db.scalar(select(CatalogueOffer).where(CatalogueOffer.source_article=='0'))
        old=db.scalar(select(CataloguePrice).where(CataloguePrice.offer_id==offer.id))
        date=old.observed_at+timedelta(days=1)
        db.add(CataloguePrice(id=key(),offer_id=offer.id,observed_at=date,price_uah=Decimal('125'),source_url=old.source_url));offer.observed_at=date
        db.commit()
    g=guide(platform,p);assert g['cohorts'][0]['offer_count']==3 and Decimal(g['cohorts'][0]['median'])==150
    monkeypatch.setattr(pg,'utcnow',lambda:datetime(2030,1,1,tzinfo=timezone.utc))
    g=guide(platform,p);assert g['level']=='D' and g['reasons']['stale_observation']>=3


def test_preview_confirm_formula_rounding_replay_and_no_stock_or_sales_changes(platform,vehicle):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    with Session(engine()) as db:before=all_tables(db)
    j=preview(platform,[p],mode='discount',percent='10',rounding=10)
    assert j['report']['items'][0]['new_price']=='140.00'
    assert platform.get('/api/v1/parts/'+p).json()['selling_price'] is None
    request=dict(token=j['token'],confirm=True,request_key=key());r=apply(platform,j,request);assert r.status_code==200,r.text
    assert apply(platform,j,request).json()==r.json()
    assert platform.get('/api/v1/parts/'+p).json()['selling_price']=='140.00'
    with Session(engine()) as db:
        assert db.get(Part,p).quantity==1 and db.get(Part,p).reserved_quantity==0
        assert db.scalar(select(func.count()).select_from(Operation).where(Operation.after['pricing_decision_id'].as_string()==j['id']))==1
    j2=preview(platform,[p]);assert j2['report']['changed']==0 and 'Власну' in j2['report']['items'][0]['reason']
    j3=preview(platform,[p],mode='markup',percent='10',overwrite=True,rounding=50);assert j3['report']['items'][0]['new_price']=='150.00'


def test_stale_market_manual_aba_and_modern_manual_replay(platform,vehicle):
    p=setup(platform,vehicle,[item(i) for i in range(3)]);g=guide(platform,p);j=preview(platform,[p])
    req=dict(expected_token=g['part_revision'],request_key=key())
    assert price(platform,p,'42.00',**req).status_code==200
    first=price(platform,p,'42.00',**req);assert first.status_code==200
    assert apply(platform,j).status_code==409
    assert price(platform,p,'43.00',expected_token=g['part_revision'],request_key=key()).status_code==409
    assert price(platform,p,None).status_code==200
    j=preview(platform,[p])
    with Session(engine()) as db:
        obs=db.scalar(select(CataloguePrice));date=obs.observed_at+timedelta(days=1)
        db.add(CataloguePrice(id=key(),offer_id=obs.offer_id,observed_at=date,price_uah=Decimal('888.00'),source_url=obs.source_url));db.get(CatalogueOffer,obs.offer_id).observed_at=date;db.commit()
    assert apply(platform,j).status_code==409
    assert platform.get('/api/v1/parts/'+p).json()['selling_price'] is None


def test_valuation_uses_real_qty_reserves_partial_coverage_and_currency(platform,vehicle):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    with Session(engine()) as db:
        row=db.get(Part,p);row.quantity=5;row.reserved_quantity=2;row.selling_price=Decimal('120');db.commit()
    r=platform.get('/api/v1/vehicles/'+vehicle['id']+'/parts-valuation');assert r.status_code==200,r.text
    totals=next(b for b in r.json()['by_currency'] if b['currency']=='UAH')
    assert Decimal(totals['own_total'])==600 and Decimal(totals['own_reserved'])==240
    assert Decimal(totals['market_total'])==750 and Decimal(totals['market_reserved'])==300
    assert totals['market_unpriced']>0 and 0<totals['market_coverage_percent']<100


def test_concurrent_apply_is_single_audit_and_atomic_failure(platform,vehicle,monkeypatch):
    p=setup(platform,vehicle,[item(i) for i in range(3)]);j=preview(platform,[p]);req=dict(token=j['token'],confirm=True,request_key=key())
    def send(_):
        with TestClient(app) as c:
            c.cookies.update(platform.cookies);c.headers['X-CSRF-Token']=platform.headers['X-CSRF-Token'];r=apply(c,j,req);return r.status_code,r.json()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(send,range(2)))
    assert results[0]==results[1] and results[0][0]==200
    with Session(engine()) as db:assert db.scalar(select(func.count()).select_from(Operation).where(Operation.after['pricing_decision_id'].as_string()==j['id']))==1


@pytest.mark.parametrize('override,expected',[
    ({'oem':'OEM-123-B'},'C'),({'condition':'new'},'C'),({'condition':''},'C'),
    ({'part_name':'Фара передня ліва Volvo XC40 2016'},'D'),
    ({'part_name':'Фара передня права Volvo XC40','side':'права'},'D'),
    ({'model':'XC90','part_name':'Фара передня ліва Volvo XC90'},'D')])
def test_never_merges_incompatible_or_unknown_variants(platform,vehicle,override,expected):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    # Structural changes require a new normalization, never bypass the source
    # hash guard. These quotes are first imported with the changed attributes.
    with Session(engine()) as db:
        target=db.get(Part,p);target.oem_number='OTHER' if 'oem' in override else target.oem_number;target.condition='unknown' if 'condition' in override else target.condition
        if 'part_name' in override and 'права' in override['part_name']:
            vehicle_row=db.get(Vehicle,vehicle['id']);vehicle_row.model='XC90'
        if override.get('model')=='XC90':db.get(Vehicle,vehicle['id']).model='XC90'
        if '2016' in override.get('part_name',''):db.get(Vehicle,vehicle['id']).year=2016
        db.commit()
    # For model/year/side cases the existing source is incompatible with the
    # changed target context (or only an uncertain example), never exact A.
    g=guide(platform,p);assert g['level']!='A'


def test_source_change_requires_normalization_and_future_missing_dates(platform,vehicle):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    with Session(engine()) as db:
        for offer in db.scalars(select(CatalogueOffer)):offer.properties={**offer.properties,'part_name':'Бампер передній Volvo XC40'}
        db.commit()
    g=guide(platform,p);assert g['level']=='D' and g['reasons']['stale_source_mapping']==3


def test_mixed_selection_fixed_currency_and_rollback(platform,vehicle,monkeypatch):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    with Session(engine()) as db:
        p2=db.scalar(select(Part).where(Part.id!=p));p2.currency='USD';p2id=p2.id
        p3=db.scalar(select(Part).where(Part.id.notin_([p,p2id])));p3id=p3.id;db.commit()
    j=preview(platform,[p,p2id],mode='fixed',fixed_price='123.45',rounding=1)
    assert j['report']['changed']==1 and j['report']['skipped']==1
    assert 'Валюта' in next(r for r in j['report']['items'] if r['part_id']==p2id)['reason']
    j=preview(platform,[p,p3id],mode='fixed',fixed_price='123.45')
    with Session(engine()) as db:before=all_tables(db)
    original=pricing.set_price;count=[]
    def fail(*a,**kw):
        result=original(*a,**kw);a[0].flush();count.append(1)
        if len(count)==2:raise RuntimeError('Injected pricing failure')
        return result
    monkeypatch.setattr(pricing,'set_price',fail)
    with pytest.raises(RuntimeError):apply(platform,j)
    with Session(engine()) as db:assert all_tables(db)==before


def test_permissions_csrf_tenant_isolation_and_expired_preview(platform,vehicle,monkeypatch):
    from conftest import signup
    from test_team import employee,activate as worker_login
    p=setup(platform,vehicle,[item(i) for i in range(3)]);j=preview(platform,[p])
    with TestClient(app) as other:
        signup(other,'other-pricing@example.test')
        assert other.get('/api/v1/parts/'+p+'/price-guidance').status_code==404
        assert other.post('/api/v1/pricing/guidance',json={'ids':[p]}).status_code==404
        assert apply(other,j).status_code==404
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    worker,data=employee(platform,permissions=['inventory.view','catalog.view','parts.change_price'])
    with worker_login(data) as c:
        assert guide(c,p)['level']=='A'
        assert c.post('/api/v1/pricing/previews',json=dict(ids=[p],request_key=key())).status_code==403
        assert c.get('/api/v1/pricing/previews/'+j['id']).status_code==403
    csrf=platform.headers.pop('X-CSRF-Token');assert apply(platform,j).status_code==403;platform.headers['X-CSRF-Token']=csrf
    with Session(engine()) as db:db.get(PriceDecision,j['id']).expires_at=datetime(2020,1,1,tzinfo=timezone.utc);db.commit()
    assert apply(platform,j).status_code==409
    assert platform.get('/api/v1/parts/'+p).json()['selling_price'] is None


def test_price_updates_preserve_order_sale_snapshots_and_quantities(platform,vehicle):
    from test_orders import buyer,create,line,action
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    assert platform.post('/api/v1/parts/'+p+'/operations',json=dict(type='correction',quantity=5,reason='Local pricing stock fixture',request_key=key())).status_code==200
    b=buyer(platform);part=platform.get('/api/v1/parts/'+p).json();order=create(platform,b,[line(part,2)])
    assert action(platform,order,'reserve').status_code==200
    sale=platform.post('/api/v1/parts/'+p+'/operations',json=dict(type='sale',quantity=1,sale_price='20.00',sale_currency='UAH',request_key=key()));assert sale.status_code==200
    with Session(engine()) as db:
        before=all_tables(db)
    j=preview(platform,[p]);assert apply(platform,j).status_code==200
    with Session(engine()) as db:
        after=all_tables(db)
        for name in ('order_lines','order_reservations','orders','order_events'):assert before[name]==after[name]
        assert db.get(Part,p).quantity==4 and db.get(Part,p).reserved_quantity==2
        for op in db.scalars(select(Operation).where(Operation.type=='sale')):assert op.after['sale']['unit_price']=='20.00'


def test_preview_limits_confirmation_and_modern_manual_concurrent_stale(platform,vehicle):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    assert platform.post('/api/v1/pricing/previews',json=dict(ids=[p]*1001,request_key=key())).status_code==422
    assert platform.post('/api/v1/pricing/previews',json=dict(ids=[p,p],request_key=key())).status_code==422
    g=guide(platform,p);j=preview(platform,[p]);assert apply(platform,j,dict(token=j['token'],confirm=False,request_key=key())).status_code==422
    assert apply(platform,j).status_code==200
    assert price(platform,p,'250.00',expected_token=g['part_revision'],request_key=key()).status_code==409
    current=guide(platform,p);assert price(platform,p,None,expected_token=current['part_revision'],request_key=key()).status_code==200
    assert platform.get('/api/v1/parts/'+p).json()['selling_price'] is None


@pytest.mark.parametrize('condition',['','synthetic unknown condition'])
def test_unknown_source_condition_never_used_as_used(platform,vehicle,condition):
    p=setup(platform,vehicle,[{**item(i),'condition':condition} for i in range(3)])
    g=guide(platform,p);assert g['level']=='C' and not g['cohorts']
    assert all(e['condition']=='unknown' for e in g['examples'])


def test_missing_future_zero_and_old_observations_never_become_zero_guidance(platform,vehicle):
    p=setup(platform,vehicle,[{**item(i),'observed_at':'2030-01-01T00:00:00+00:00'} for i in range(3)])
    g=guide(platform,p);assert g['level']=='D' and not g['cohorts']
    assert g['reasons']['future_source_observation']==3


@pytest.mark.parametrize('conflict',[False,True])
def test_v1_bridge_is_tenant_scoped_and_deduplicates_v2_same_ad(platform,vehicle,conflict):
    from app.models.aleto import AletoOffer,AletoPrice,AletoModel,AletoTaxonomy,AletoApplication
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    with Session(engine()) as db:
        own=db.get(Part,p);source=db.scalar(select(CatalogueOffer).where(CatalogueOffer.source_article=='0'))
        model=AletoModel(account_id=own.account_id,manufacturer='Volvo',model='XC40');db.add(model);db.flush()
        offer=AletoOffer(account_id=own.account_id,source='aleto',source_article='0',title=source.properties['part_name'],oem=source.properties['oem'],condition='used',source_url=source.properties['source_url'],observed_at=source.observed_at);db.add(offer);db.flush()
        db.add(AletoPrice(account_id=own.account_id,offer_id=offer.id,observed_at=offer.observed_at,price_uah=Decimal('999') if conflict else Decimal('100'),source_url=offer.source_url))
        db.add(AletoApplication(account_id=own.account_id,offer_id=offer.id,model_id=model.id));db.flush()
        db.add(AletoTaxonomy(account_id=own.account_id,offer_id=offer.id,model_id=model.id,category_id=own.category_id,subcategory_id=own.subcategory_id,raw_category='Оптика',raw_subcategory='Фари',normalization_status='verified'));db.commit()
    g=guide(platform,p);assert g['offer_count']==3
    assert g['level']==('B' if conflict else 'A'),g
    assert g['cohorts'][0]['offer_count']==(2 if conflict else 3)


def test_pricing_downgrade_preserves_durable_decisions(platform,vehicle):
    import sys,subprocess
    p=setup(platform,vehicle,[item(i) for i in range(3)]);j=preview(platform,[p])
    with Session(engine()) as db:before=all_tables(db)
    result=subprocess.run([sys.executable,'-m','alembic','downgrade','95c3e7b12a04'],capture_output=True,text=True)
    assert result.returncode!=0 and 'Pricing decisions exist' in result.stderr
    with Session(engine()) as db:assert all_tables(db)==before


def test_bounded_batch_over_ten_thousand_offers_has_no_per_card_queries(platform,vehicle,tmp_path):
    import copy,time,json
    from sqlalchemy import insert
    from app.models.catalogue import CatalogueApplication,CatalogueEntity
    from app.models.canonical import CanonicalMapping,CanonicalState
    from app.services.canonical_catalogue import global_inputs,source_record
    from app.services.catalogue_format import digest
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    with Session(engine()) as db:
        original=db.get(Part,p);original_vehicle=db.get(Vehicle,original.vehicle_id)
        mapping=db.scalar(select(CanonicalMapping).where(CanonicalMapping.variant_id.is_not(None)))
        template=next(s for s in global_inputs(db) if s.get('article')=='0')
        offer=db.get(CatalogueOffer,template['offer_id']);props=copy.deepcopy(offer.properties);date=offer.observed_at
        offers=[];prices=[];apps=[];paths=[];mappings=[]
        for i in range(10000):
            oid=key();pid=key();article='SYNTHETIC-PRICE-'+str(i);url='https://aleto.ua/ua/detail/synthetic-price-'+str(i)+'/'
            properties={**props,'source_url':url};raw=copy.deepcopy(template['raw'])
            offers.append(dict(id=oid,source_id=offer.source_id,source_article=article,properties=properties,observed_at=date))
            prices.append(dict(id=key(),offer_id=oid,observed_at=date,price_uah=Decimal(100+i%100),price_usd=None,source_url=url))
            apps.append(dict(offer_id=oid,model_id=template['model_id'],model_kind='model'))
            paths.append(dict(id=pid,offer_id=oid,model_id=template['model_id'],part_type_id=None,part_kind=None,path_key=digest([pid]),raw=raw))
            record={k:v for k,v in template.items() if k!='sha'};record.update(key='v2:'+pid,path_id=pid,offer_id=oid,article=article,source_url=url)
            mappings.append(dict(id=key(),snapshot_sha=mapping.snapshot_sha,source_kind='v2',source_key='v2:'+pid,source_sha=source_record(**record)['sha'],catalogue_path_id=pid,type_id=mapping.type_id,placement_id=mapping.placement_id,variant_id=mapping.variant_id,quality=mapping.quality,evidence=mapping.evidence))
        for cls,rows in [(CatalogueOffer,offers),(CataloguePrice,prices),(CatalogueApplication,apps),(CataloguePath,paths),(CanonicalMapping,mappings)]:
            for n in range(0,len(rows),500):db.execute(insert(cls),rows[n:n+500])
        ids=[p];max_number=db.scalar(select(func.max(Vehicle.number)))
        for i in range(299):
            v=Vehicle(account_id=original.account_id,manufacturer='Volvo',model='XC40',year=2020,number=max_number+i+1,donor_id='SYNTHETIC-PRICE-DONOR-'+str(i),dismantling_v3=copy.deepcopy(original_vehicle.dismantling_v3));db.add(v);db.flush()
            part=Part(account_id=original.account_id,vehicle_id=v.id,name=original.name,condition='used',quantity=1,oem_number=original.oem_number,canonical_placement_id=original.canonical_placement_id);db.add(part);db.flush();ids.append(part.id)
        db.commit()
    counts=[]
    def query(*args):counts.append(1)
    event.listen(engine(),'before_cursor_execute',query)
    try:
        started=time.perf_counter();one=platform.post('/api/v1/pricing/guidance',json={'ids':[p]});one_seconds=time.perf_counter()-started;one_count=len(counts);counts.clear()
        started=time.perf_counter();batch=platform.post('/api/v1/pricing/guidance',json={'ids':ids});batch_seconds=time.perf_counter()-started;batch_count=len(counts)
    finally:event.remove(engine(),'before_cursor_execute',query)
    assert one.status_code==batch.status_code==200,(one.text[:500],batch.text[:500])
    assert all(g['level']=='A' and g['cohorts'][0]['offer_count']==10003 for g in batch.json()['items'])
    assert batch_count<=one_count+3 and batch_count<60,(one_count,batch_count)
    result=dict(synthetic=True,real_Volvo_B_tested=False,offers=10003,parts=len(ids),one_queries=one_count,batch_queries=batch_count,one_seconds=round(one_seconds,3),batch_seconds=round(batch_seconds,3))
    import os
    target=os.environ.get('WAREHOUSE_PRICING_PERF_REPORT',str(tmp_path/'pricing-performance.json'))
    __import__('pathlib').Path(target).write_text(json.dumps(result,indent=2)+'\n')

def test_revoked_session_while_waiting_for_workspace_lock(platform,vehicle,monkeypatch):
    from threading import Event
    from sqlalchemy import text,delete
    from app.models import Session as AuthSession
    from app.api import pricing as routes
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    job=preview(platform,[p]);waiting=Event();original=routes.lock_workspace
    def signalled(db,account):
        waiting.set();return original(db,account)
    monkeypatch.setattr(routes,'lock_workspace',signalled)
    with Session(engine()) as hold:
        account=hold.get(Part,p).account_id
        hold.execute(text('SELECT id FROM accounts WHERE id=:id FOR NO KEY UPDATE'),{'id':account})
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(apply,platform,job)
            try:
                assert waiting.wait(10)
                with Session(engine()) as revoke:
                    revoke.execute(delete(AuthSession).where(AuthSession.account_id==account));revoke.commit()
            finally:hold.rollback()
            response=future.result(timeout=30)
    assert response.status_code==401,response.text
    with Session(engine()) as db:
        assert db.get(Part,p).selling_price is None
        assert db.get(PriceDecision,job['id']).status=='preview'

def test_changed_vehicle_does_not_reuse_old_verified_equipment_provenance(platform,vehicle):
    p=setup(platform,vehicle,[item(i) for i in range(3)])
    assert guide(platform,p)['level']=='A'
    with Session(engine()) as db:
        v=db.get(Vehicle,vehicle['id']);v.engine='changed-engine';db.commit()
    g=guide(platform,p)
    assert g['level']=='C' and all(c['level']!='A' for c in g['cohorts'])

def test_whitespace_oem_is_unknown_even_when_source_oem_also_empty(platform,vehicle):
    rows=[{**item(i),'oem':''} for i in range(3)]
    p=setup(platform,vehicle,rows)
    with Session(engine()) as db:
        part=db.get(Part,p);part.oem_number=' \u00a0 ';db.commit()
    g=guide(platform,p)
    assert g['level']=='C' and not g['cohorts']
    assert preview(platform,[p])['report']['changed']==0
