"""Explicit localhost-only browser harness; all VIN/catalogue data below SYNTHETIC."""
import os
from urllib.parse import urlsplit
p=urlsplit(os.getenv('WAREHOUSE_DATABASE_URL',''))
if os.getenv('WAREHOUSE_E2E')!='1' or os.getenv('WAREHOUSE_ENV')!='local' or p.hostname!='127.0.0.1' or p.port!=55441 or not p.path.endswith('_test'):
    raise RuntimeError('Dedicated localhost test database only')
os.environ.update(ASSEMBLY_INVENTORY_ENABLED='false',WAREHOUSE_CATALOGUE_WORKER_ENABLED='false',WAREHOUSE_COOKIE_SECURE='false',PLAN_PARTS_ENABLED='false')
from app.main import app
from app.services import vin_lookup,unified_catalogue as catalogue
from copy import deepcopy

def lookup(vin):
    return dict(vin=vin,source='OFFLINE SYNTHETIC BROWSER FIXTURE',vehicle=dict(manufacturer='Volvo',model='XC90 (synthetic)',year=2016,engine='TEST ENGINE'),additional={},available_fields=['manufacturer','model','year','engine'],field_sources={},message='Локальні синтетичні дані; не live декодування VIN')
vin_lookup.lookup=lookup
payload=dict(schema='carpot.vehicle.plan.v1',manufacturer_id=120,model_id=13084,car_id=107555,modification={'id':107555,'description':'TEST MODIFICATION, NOT REAL FITMENT'},source_snapshot_sha='a'*64,coverage='partial',coverage_verified=False,taxonomy_status='reviewed',observed_at='2026-11-11T00:00:00+00:00',photos='not_exported',categories=[dict(product_id=1,name_source='Synthetic starter',name_uk='Тестовий стартер',category_path=['Електрика та електроніка','Стартери та генератори','Стартери'],kind='part',mapping_reviewed_by='fixture',article_count=0),dict(product_id=2,name_source='Synthetic lamp',name_uk='Тестова фара',category_path=['Освітлення','Передні фари','Фари'],kind='part',mapping_reviewed_by='fixture',article_count=0)])
catalogue.CatalogueAdapter.directory=lambda *a,**k:dict(items=[dict(manufacturer='Volvo',manufacturer_id=120,model='XC90 (synthetic)',model_id=13084,generation='II (fixture)',source_modification_id=107555,snapshot_sha='a'*64,modification=payload['modification'],coverage='partial',type_count=2,article_count=0,oem_links=0)],next_after=None)
catalogue.CatalogueAdapter.plan=lambda *a,**k:dict(payload=deepcopy(payload))
