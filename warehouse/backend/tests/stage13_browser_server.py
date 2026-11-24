"""Stage 13 browser fixture backed by the real Warehouse routes and a disposable DB."""
import os
from urllib.parse import urlsplit

database = urlsplit(os.getenv("WAREHOUSE_DATABASE_URL", ""))
if (os.getenv("WAREHOUSE_E2E") != "1" or os.getenv("WAREHOUSE_ENV") != "local"
        or database.hostname != "127.0.0.1" or not database.path.endswith("_test")):
    raise RuntimeError("Stage 13 browser fixtures require local disposable PostgreSQL")

from app.main import app
from app.services import unified_catalogue, vin_lookup
from test_stage13_vin_resolution import Source, decoded

source = Source()
vin_lookup.lookup = lambda vin, *, public_only: decoded(vin)
unified_catalogue.CatalogueAdapter.get = lambda self, path, params: source.get(path, params)
