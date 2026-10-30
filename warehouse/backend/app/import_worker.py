"""Independent private worker. Waits for API-owned migrations; never migrates."""
import argparse,logging,os,signal,threading,time
from sqlalchemy import create_engine,text
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url
from app.config import database_url
from app.staging import migration_heads
from app.services.import_runner import process_one

log=logging.getLogger('warehouse.import-worker')
def schema_ready(engine):
    try:
        with engine.connect() as db:
            if frozenset(db.execute(text('SELECT version_num FROM alembic_version')).scalars())!=migration_heads():return False
            db.execute(text('SELECT id FROM import_jobs LIMIT 0'));db.execute(text('SELECT id FROM import_job_events LIMIT 0'));return True
    except Exception:return False

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--once',action='store_true');args=parser.parse_args()
    u=make_url(database_url())
    if os.getenv('WAREHOUSE_ENV')!='staging' and not (u.host=='127.0.0.1' and (u.database or '').endswith('_test')):raise SystemExit('Worker requires staging environment or dedicated loopback test DB')
    engine=create_engine(database_url(),poolclass=NullPool,connect_args={'connect_timeout':5});stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):signal.signal(sig,lambda *_:stop.set())
    deadline=time.monotonic()+120
    while not stop.is_set() and not schema_ready(engine):
        if time.monotonic()>=deadline:raise SystemExit('Schema not ready; deploy API migrations first')
        stop.wait(1)
    try:
        while not stop.is_set():
            try:worked=process_one(engine,stop)
            except Exception:log.warning('Worker database/lease unavailable; no application data applied');worked=False
            if args.once:break
            if not worked:stop.wait(1)
    finally:engine.dispose()
if __name__=='__main__':logging.basicConfig(level=logging.INFO);main()
