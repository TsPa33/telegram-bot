from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from conftest import signup
from test_team import employee,activate,patch


def test_summary_pagination_tenant_and_visibility(logged,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    admin,credentials=employee(logged,['team.view','team.manage_managers'],role='ADMIN')
    manager,_=employee(logged,[])
    assert patch(logged,manager,is_active=False).status_code==200
    with TestClient(app) as other:
        signup(other,str(uuid4())+'@example.test')
        employee(other,[])
    s=logged.get('/api/v1/team/summary').json()
    assert s=={'total':3,'active':2,'blocked':1,'by_role':{'DIRECTOR':1,'ADMIN':1,'MANAGER':1},'scope':'workspace'}
    assert logged.get('/api/v1/team?limit=1').json()['total']==3
    with activate(credentials) as c:
        assert c.get('/api/v1/team/summary').json()=={'total':1,'active':0,'blocked':1,'by_role':{'DIRECTOR':0,'ADMIN':0,'MANAGER':1},'scope':'visible_managers'}
    _,creds=employee(logged,[])
    with activate(creds) as c:
        assert c.get('/api/v1/team/summary').status_code==403


def test_currency_vehicle_values_and_financial_redaction(logged,vehicle,monkeypatch):
    monkeypatch.setenv('WAREHOUSE_TEAM_CREATION_ENABLED','true')
    for currency,price in [('UAH','12.34'),('USD','5.67')]:
        p=logged.post('/api/v1/parts',json={'name':'Оцінка '+currency,'vehicle_id':vehicle['id'],'selling_price':price,'currency':currency}).json()
        assert logged.post('/api/v1/parts/'+p['id']+'/operations',json={'type':'receipt','quantity':2,'reason':'Local integration'}).status_code==200
    dashboard=logged.get('/api/v1/dashboard').json()
    values={r['currency']:r['value'] for r in dashboard['vehicle_valuation_by_currency']}
    assert all('№'+str(vehicle['number']) in r['name'] for r in dashboard['vehicle_valuation_by_currency'])
    from decimal import Decimal
    assert {c:Decimal(v) for c,v in values.items()}=={'UAH':Decimal('24.68'),'USD':Decimal('11.34')}
    _,creds=employee(logged,['analytics.view'])
    with activate(creds) as c:
        data=c.get('/api/v1/dashboard').json()
        assert 'vehicle_valuation_by_currency' not in data and 'valuation_by_currency' not in data
        assert data['available_units']==4
