"""Local synthetic UI acceptance driver. Never imported by the operational ASGI factory."""
import os,hmac
from decimal import Decimal
from uuid import uuid4
from fastapi import HTTPException,Request
from pydantic import BaseModel
from bot.billing.db import validate_disposable_dsn
from bot.billing.storage import OperationalDatabase,migrate_all
from bot.billing.global_core import GlobalBilling
from bot.billing.liqpay_provider import ProviderProfile
from bot.billing.api import create_app

if os.getenv('WAREHOUSE_E2E')!='1':raise RuntimeError('Explicit local browser acceptance only')
dsn=os.environ['CARPOT_BILLING_BROWSER_DSN'];validate_disposable_dsn(dsn)
migrator=OperationalDatabase(dsn,environment='sandbox',role='migrator',disposable=True);migrate_all(migrator)
db=OperationalDatabase(dsn,environment='sandbox',disposable=True);GlobalBilling(db).seed_catalogue()
key=os.environ['WAREHOUSE_BILLING_SERVICE_KEY'].encode()
fixture_key=os.environ['BILLING_BROWSER_FIXTURE_KEY']
profile=ProviderProfile('sandbox','sandbox_global_browser_public','sandbox_global_browser_private','https://warehouse.example.test/settings?section=payments','https://billing.example.test/v1/liqpay/callback')
app=create_app(db,profile,peer_keys={'warehouse':key},checkout_enabled=True)

class Confirmation(BaseModel):
    order_id:str

def authorize(request):
    if not hmac.compare_digest(request.headers.get('X-Fixture-Key',''),fixture_key):raise HTTPException(403)

@app.post('/__fixture/confirm')
def confirm(data:Confirmation,request:Request):
    authorize(request)
    payments=app.state.payments
    with db.transaction() as c:row=payments._row(c,data.order_id)
    payload=dict(version=7,public_key=profile.public_key,action='pay',order_id=data.order_id,amount=f"{row['amount_minor']//100}.{row['amount_minor']%100:02d}",currency='UAH',status='sandbox',payment_id='synthetic-'+uuid4().hex)
    return {'classification':payments.callback(**payments.provider.sign(payload)),'synthetic_only':True}

@app.get('/__fixture/order/{order}')
def check(order:str,request:Request):
    authorize(request)
    with db.transaction() as c:
        row=app.state.payments._row(c,order)
        c.execute('SELECT count(*) AS n FROM billing.settlements WHERE invoice_id=%s',(row['invoice_id'],));settlements=c.fetchone()['n']
        c.execute('SELECT count(*) AS n FROM billing.provider_orders o JOIN billing.intents i ON i.id=o.intent_id WHERE i.invoice_id=%s',(row['invoice_id'],));orders=c.fetchone()['n']
    return dict(settlements=settlements,orders=orders,amount_minor=row['amount_minor'],synthetic_only=True)
