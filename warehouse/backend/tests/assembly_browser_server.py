"""Local browser harness only; refuses all non-test PostgreSQL targets."""
import os
from urllib.parse import urlsplit
p=urlsplit(os.getenv('WAREHOUSE_DATABASE_URL',''))
if os.getenv('WAREHOUSE_E2E')!='1' or os.getenv('WAREHOUSE_ENV')!='local' or p.hostname!='127.0.0.1' or p.port!=55441 or not p.path.endswith('_test'):
    raise RuntimeError('Only dedicated localhost assembly test DB allowed')
os.environ.update(ASSEMBLY_INVENTORY_ENABLED=os.getenv('WAREHOUSE_E2E_ASSEMBLY_ENABLED','true'),WAREHOUSE_CATALOGUE_WORKER_ENABLED='false',WAREHOUSE_COOKIE_SECURE='false',PLAN_PARTS_ENABLED='false',WAREHOUSE_DEEPL_API_KEY='')
from fastapi import Request,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.main import app
from app.db import engine
from app.models import Account,Session as LoginSession,Vehicle,Part,DismantlingItem,now
from app.services.auth import digest
from app.services.assemblies import attach,confirm,preview

@app.post('/__assembly_fixture')
def seed(request:Request,scenario:str='assembly'):
    with Session(engine()) as db:
        login=db.get(LoginSession,digest(request.cookies.get('warehouse_session','')))
        if not login or login.expires_at<=now() or digest(request.headers.get('X-CSRF-Token',''))!=login.csrf_hash:raise HTTPException(403)
        account=db.get(Account,login.account_id)
        if not account.email.endswith('@example.test'):raise HTTPException(403)
        db.info['actor_id']=account.id
        v=Vehicle(account_id=account.id,manufacturer='Volvo',model='XC90 II (synthetic)',year=2018,number=1,donor_id='SYNTHETIC-ASSEMBLY',dismantling_v3={'global_selection':{'car_id':107555}})
        db.add(v);db.flush();nodes=[]
        if scenario=='partial113':
            from types import SimpleNamespace
            from app.services.unified_catalogue import persist
            from app.services.assemblies import digest as plan_digest
            payload=dict(schema='carpot.volvo.plan.v2',manufacturer_id=120,model_id=13084,car_id=107555,modification={'id':107555,'description':'T6 AWD — local fixture'},coverage='partial',coverage_verified=False,taxonomy_status='draft',source_snapshot_sha='a'*64,observed_at='2026-11-10T10:00:00+00:00',categories=[dict(product_id=1000+i,name_source=f'Local part {i}',name_uk=f'Локальна деталь {i}',kind='review' if i<2 else 'part',category_path=[] if i<2 else ['Освітлення','Передні фари','Лампа'],article_count=i%4) for i in range(113)])
            persist(db,SimpleNamespace(workspace_account_id=account.id),v,dict(payload=payload,sha256=plan_digest(payload)),allow_partial=True)
            db.commit()
            return dict(vehicle_id=v.id,scenario='partial113')
        for i in range(552):
            part=None
            if i<13:
                part=Part(account_id=account.id,vehicle_id=v.id,name='Двері передні ліві в зборі' if i==0 else f'Компонент дверей {i}',quantity=1,reserved_quantity=0,individually_tracked=True)
                db.add(part);db.flush()
            category=('body','Кузов та зовнішні деталі') if i<13 else [('body','Кузов та зовнішні деталі'),('engine','Двигун та його системи'),('electric','Електрика та електроніка'),('interior',"Салон та інтер’єр")][i%4]
            node=DismantlingItem(account_id=account.id,vehicle_id=v.id,name=part.name if part else f'Потенційна позиція {i}',source='assembly.fixture',catalog_key=str(i),category_key=category[0],category_name=category[1],subcategory_key='door',subcategory_name='Двері',quantity=1,part_id=part.id if part else None)
            db.add(node);db.flush();nodes.append(node)
        for node in nodes[1:13]:attach(db,account.id,v.id,nodes[0].id,node.id)
        confirm(db,account.id,v.id,nodes[0].id,preview(db,account.id,nodes[0].id)['token'])
        db.commit()
        return dict(vehicle_id=v.id,root_id=nodes[0].id,part_id=nodes[0].part_id)
