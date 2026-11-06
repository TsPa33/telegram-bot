"""Focused start-flow regression: disposable local DB, no paid source calls."""
from sqlalchemy import text,select,func
from sqlalchemy.orm import Session
from app.main import app
from app.db import engine
from app.models import Part,Operation,PlanPartsResponse
from app.api.plan_parts import plan_parts_client
from app.services.plan_parts import CatalogPartType
from test_v3_release_audit import all_tables
from uuid import uuid4


def test_free_restoration_persists_catalogue_without_stock(logged,vehicle):
    with engine().begin() as db:db.execute(text('UPDATE vehicles SET ktype=123 WHERE id=:id'),{'id':vehicle['id']})
    calls=[]
    class SavedProvider:
        def recover_categories(self,*args):calls.append('recover');return [CatalogPartType(pt_id=10,name='Starter',article_count=3)]
        def categories(self,*args):raise AssertionError('No paid request')
    app.dependency_overrides[plan_parts_client]=SavedProvider
    url='/api/v1/plan-parts/categories/recover?vehicle_id='+vehicle['id']+'&ktype=123'
    try:
        assert logged.post(url).status_code==200
        again=logged.post(url);assert again.status_code==200 and again.json()['from_saved']
        data=logged.get('/api/v1/plan-parts/workspace?vehicle_id='+vehicle['id']).json()
        assert len(data['categories'])==1 and calls==['recover']
        with Session(engine()) as db:
            assert db.scalar(select(func.count()).select_from(Part))==0
            assert db.scalar(select(func.count()).select_from(Operation).where(Operation.type=='receipt'))==0
    finally:app.dependency_overrides.pop(plan_parts_client,None)


def test_saved_modifications_are_vehicle_scoped_and_read_only(logged,vehicle):
    owner=logged.get('/api/v1/auth/me').json()['id']
    with Session(engine()) as db:
        for model,ktype in [(vehicle['model'],123),('Different model',456)]:
            db.add(PlanPartsResponse(account_id=owner,actor_id=owner,vehicle_id=vehicle['id'],resource='ktype',parameters={'brand':vehicle['manufacturer'],'model':model,'year':vehicle['year']},context_hash=str(uuid4()),request_key=str(uuid4()),status='validated',normalized=[{'ktype':ktype,'modification':'Synthetic saved modification'}],metadata_json={}))
        db.commit();before=all_tables(db)
    response=logged.get('/api/v1/plan-parts/workspace?vehicle_id='+vehicle['id']);assert response.status_code==200,response.text
    assert [r['ktype'] for r in response.json()['saved_modifications']]==[123]
    with Session(engine()) as db:assert before==all_tables(db)
