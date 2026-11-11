"""Disposable PostgreSQL only: one checkout, one transaction, one stock ledger."""
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from app.db import engine
from app.models import Order
from sqlalchemy.orm import Session
from test_orders import buyer,stocked,line,state

@pytest.mark.parametrize('action,quantity,reserved',[('draft',3,0),('reserve',3,2),('sell',1,0)])
def test_checkout_replay(logged,vehicle,action,quantity,reserved):
    p=stocked(logged,vehicle);b=buyer(logged)
    data=dict(request_key=str(uuid4()),buyer_id=b['id'],lines=[line(p,2)],checkout_action=action,confirm_sale=action=='sell')
    first=logged.post('/api/v1/orders/checkout',json=data)
    assert first.status_code==201,first.text
    again=logged.post('/api/v1/orders/checkout',json=data)
    assert again.status_code==201 and again.json()==first.json()
    actual=state(logged,p)
    assert actual['quantity']==quantity and actual['reserved_quantity']==reserved
    assert bool(first.json()['sold_at'])==(action=='sell')

def test_checkout_failure_leaves_no_order_or_partial_deduction(logged,vehicle):
    b=buyer(logged);p=stocked(logged,vehicle);q=stocked(logged,vehicle,quantity=1,name='Other')
    data=dict(request_key=str(uuid4()),buyer_id=b['id'],lines=[line(p),line(q,2)],checkout_action='sell',confirm_sale=True)
    r=logged.post('/api/v1/orders/checkout',json=data)
    assert r.status_code==409,r.text
    assert state(logged,p)['quantity']==3 and state(logged,q)['quantity']==1
    assert logged.get('/api/v1/orders').json()['total']==0

def test_checkout_requires_explicit_sale_confirmation(logged,vehicle):
    p=stocked(logged,vehicle);b=buyer(logged)
    r=logged.post('/api/v1/orders/checkout',json=dict(request_key=str(uuid4()),buyer_id=b['id'],lines=[line(p)],checkout_action='sell'))
    assert r.status_code==422
    assert state(logged,p)['quantity']==3

@pytest.mark.parametrize('action,required',[('draft',{'orders.create'}),('reserve',{'orders.create','orders.fulfill'}),('sell',{'orders.create','orders.fulfill','sales.create'})])
def test_checkout_permission_contract(action,required):
    from app.permissions import route_permissions
    assert set(route_permissions('POST','/api/v1/orders/checkout',{'checkout_action':action}))==required

def test_checkout_csrf_and_workspace(logged,vehicle):
    from fastapi.testclient import TestClient
    from app.main import app
    from conftest import signup
    p=stocked(logged,vehicle);b=buyer(logged)
    data=dict(request_key=str(uuid4()),buyer_id=b['id'],lines=[line(p)],checkout_action='sell',confirm_sale=True)
    assert logged.post('/api/v1/orders/checkout',json=data,headers={'X-CSRF-Token':'invalid'}).status_code==403
    with TestClient(app) as other:
        signup(other,"other502@example.test")
        assert other.post('/api/v1/orders/checkout',json=data).status_code==404
    assert state(logged,p)['quantity']==3
