"""Local browser harness. Guard and network mocks inherited from existing harness."""
from tests.vehicle_workspace_server import app
from tests.test_unified_catalogue import envelope
from app.services.unified_catalogue import CatalogueAdapter
CatalogueAdapter.plan=lambda self,car:envelope(car)
CatalogueAdapter.modifications=lambda self,model_id:dict(items=[dict(source_modification_id=car,model_id=model_id,modification={'id':car,'description':'T6 AWD','constructioninterval':'2015-'},coverage='complete_verified') for car in (107555,107556)])
