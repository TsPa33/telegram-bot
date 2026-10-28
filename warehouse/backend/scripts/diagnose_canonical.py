"""Read-only Warehouse diagnostics; uses existing WAREHOUSE_DATABASE_URL, never prints it."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db import engine
from app.models import Vehicle
from app.services.canonical_diagnostics import diagnostics
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--vehicle-id');args=p.parse_args()
with Session(engine()) as db:
    db.execute(text('SET TRANSACTION READ ONLY'))
    vehicle=db.get(Vehicle,args.vehicle_id) if args.vehicle_id else None
    if args.vehicle_id and not vehicle:raise SystemExit('Vehicle not found')
    print(json.dumps(diagnostics(db,vehicle),ensure_ascii=False,indent=2,default=str))
    db.rollback()
