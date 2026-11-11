"""Local actual-auth/PG/UI integration harness; NO mocks of inventory or auth services."""
import os
from urllib.parse import urlsplit
p=urlsplit(os.getenv('WAREHOUSE_DATABASE_URL',''))
if os.getenv('WAREHOUSE_E2E')!='1' or os.getenv('WAREHOUSE_ENV')!='local' or p.hostname!='127.0.0.1' or p.port!=55441 or p.path!='/warehouse_issue502_browser_test':
    raise RuntimeError('Issue502 dedicated localhost DB only')
os.environ.update(ASSEMBLY_INVENTORY_ENABLED='true',WAREHOUSE_CATALOGUE_WORKER_ENABLED='false',WAREHOUSE_COOKIE_SECURE='false',PLAN_PARTS_ENABLED='false')
from fastapi import Request,HTTPException
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import Account,Session as LoginSession,Vehicle,Part,DismantlingItem,now
from app.services.auth import digest

@app.post('/__issue502_fixture')
def seed(request:Request):
    with Session(engine()) as db:
        login=db.get(LoginSession,digest(request.cookies.get('warehouse_session','')))
        if not login or login.expires_at<=now() or digest(request.headers.get('X-CSRF-Token',''))!=login.csrf_hash:raise HTTPException(403)
        account=db.get(Account,login.account_id)
        if not account.email.endswith('@example.test'):raise HTTPException(403)
        v=Vehicle(account_id=account.id,manufacturer='Volvo',model='XC90 II — local QA',year=2016,number=1,donor_id='ISSUE502-SYNTHETIC')
        db.add(v);db.flush();rows=[]
        for i,(name,quantity,position) in enumerate([('Бампер (задній)',1,'задня'),('Бампер (передній)',6,'передня'),('Двері',1,'передня ліва'),('Двигун у зборі',1,'')]):
            part=Part(account_id=account.id,vehicle_id=v.id,name=name,quantity=quantity,reserved_quantity=0,condition='used',availability='present',individually_tracked=quantity==1)
            db.add(part);db.flush()
            node=DismantlingItem(account_id=account.id,vehicle_id=v.id,part_id=part.id,source='issue502.local.qa',catalog_key=str(i),name=name,quantity=quantity,position=position,category_key='body',category_name='Кузов та зовнішні деталі',subcategory_key='qa',subcategory_name='Контрольні вузли',status='dismantled',plan_v3={'inspection':'present'})
            db.add(node);db.flush();rows.append(dict(id=node.id,part_id=part.id,name=name,quantity=quantity))
        db.commit();return dict(vehicle_id=v.id,rows=rows)
