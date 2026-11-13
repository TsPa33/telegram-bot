"""Local actual-auth/PG/UI integration harness; NO mocks of inventory or auth services."""
import os
from urllib.parse import urlsplit
p=urlsplit(os.getenv('WAREHOUSE_DATABASE_URL',''))
if os.getenv('WAREHOUSE_E2E')!='1' or os.getenv('WAREHOUSE_ENV')!='local' or p.hostname!='127.0.0.1' or p.port!=55441 or p.path!='/warehouse_dismantling_v2_browser_test':
    raise RuntimeError('DismantlingV2 dedicated localhost DB only')
os.environ.update(ASSEMBLY_INVENTORY_ENABLED='true',WAREHOUSE_CATALOGUE_WORKER_ENABLED='false',WAREHOUSE_COOKIE_SECURE='false',PLAN_PARTS_ENABLED='false')
from fastapi import Request,HTTPException
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import Account,Session as LoginSession,Vehicle,Part,DismantlingItem,now
from app.services.auth import digest

@app.post('/__dv2_fixture')
def seed(request:Request):
    with Session(engine()) as db:
        login=db.get(LoginSession,digest(request.cookies.get('warehouse_session','')))
        if not login or login.expires_at<=now() or digest(request.headers.get('X-CSRF-Token',''))!=login.csrf_hash:raise HTTPException(403)
        account=db.get(Account,login.account_id)
        if not account.email.endswith('@example.test'):raise HTTPException(403)
        v=Vehicle(account_id=account.id,manufacturer='Volvo',model='XC90 II — local QA',year=2016,number=1,donor_id='DV2-SYNTHETIC')
        db.add(v);db.flush();rows=[]
        for i,(name,quantity,position) in enumerate([('Бампер (задній)',1,'задня'),('Бампер (передній)',6,'передня'),('Двері',1,'передня ліва'),('Двигун у зборі',1,'')]):
            part=Part(account_id=account.id,vehicle_id=v.id,name=name,quantity=quantity,reserved_quantity=0,condition='used',availability='present',individually_tracked=quantity==1)
            db.add(part);db.flush()
            node=DismantlingItem(account_id=account.id,vehicle_id=v.id,part_id=part.id,source='dv2.local.qa',catalog_key=str(i),name=name,quantity=quantity,position=position,category_key='body',category_name='Кузов та зовнішні деталі',subcategory_key='qa',subcategory_name='Контрольні вузли',status='dismantled',plan_v3={'inspection':'present'})
            db.add(node);db.flush();rows.append(dict(id=node.id,part_id=part.id,name=name,quantity=quantity))
        db.commit();return dict(vehicle_id=v.id,rows=rows)

@app.post('/__dv2_owner')
def local_platform_owner(request:Request):
    # Dedicated local *_test process only; no Railway variable or real account change.
    with Session(engine()) as db:
        login=db.get(LoginSession,digest(request.cookies.get('warehouse_session','')))
        if not login or login.expires_at<=now() or digest(request.headers.get('X-CSRF-Token',''))!=login.csrf_hash:raise HTTPException(403)
        account=db.get(Account,login.account_id)
        if not account.email.endswith('@example.test'):raise HTTPException(403)
        os.environ['WAREHOUSE_CATALOG_PLATFORM_ADMIN_IDS']=account.id
        return {'local_test_owner':True}


# Synthetic upstream only, the actual Warehouse API, authorization and DB are exercised.
from app.services.unified_catalogue import CatalogueAdapter
from test_unified_catalogue import envelope, detail_items
_original_plan=CatalogueAdapter.plan
_original_articles=CatalogueAdapter.articles
def pilot_plan(self,car,**kwargs):
    if car==107555 and not kwargs.get('global_source'):
        import hashlib,json
        data=envelope(car,'partial');data['payload']['categories'][0]['name_uk']='Стартер';data['payload']['categories'][0]['category_path']=['Двигун та його системи','Електрообладнання двигуна','Стартер']
        # Keep the reviewed fixture's existing valid category instead; the test row is aligned explicitly.
        data['payload']['categories'][0]['category_path']=['Освітлення','Передні фари','Стартер']
        data['sha256']=hashlib.sha256(json.dumps(data['payload'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        return data
    return _original_plan(self,car,**kwargs)
def pilot_articles(self,car,product_id,snapshot_sha,**kwargs):
    if car==107555 and product_id==106 and snapshot_sha=='a'*64 and not kwargs.get('global_source'):
        return detail_items()
    return _original_articles(self,car,product_id,snapshot_sha,**kwargs)
CatalogueAdapter.plan=pilot_plan
CatalogueAdapter.articles=pilot_articles


@app.post('/__dv2_auto_oem/{vehicle_id}')
def local_auto_oem(vehicle_id:str,request:Request):
    from app.services.auto_oem import enrich_vehicle
    with Session(engine()) as db:
        login=db.get(LoginSession,digest(request.cookies.get('warehouse_session','')))
        if not login or login.expires_at<=now() or digest(request.headers.get('X-CSRF-Token',''))!=login.csrf_hash:raise HTTPException(403)
        v=db.get(Vehicle,vehicle_id)
        if not v or v.account_id!=login.account_id:raise HTTPException(404)
        v.year=2016;v.vin='YV4A22PK2G1092943';v.fuel_type='petrol';v.drive_type='awd'
        from sqlalchemy import select
        row=db.scalar(select(DismantlingItem).where(DismantlingItem.vehicle_id==v.id,DismantlingItem.name=='Стартер'))
        if not row:raise HTTPException(404)
        row.category_name='Освітлення'
        aid=v.account_id;rid=row.id;db.commit()
    return {'count':enrich_vehicle(engine(),aid,vehicle_id),'item_id':rid}
