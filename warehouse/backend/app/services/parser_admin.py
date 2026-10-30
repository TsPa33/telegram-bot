"""R8.1 capabilities and global-owner read projection; no fetch/run/publish code."""
from sqlalchemy import select,func,text
from sqlalchemy.orm import defer
from app.models.catalogue import CatalogueSource, CatalogueOffer, CatalogueJob, CatalogueOperation, CataloguePrice
from app.models.canonical import CanonicalRun

SOURCES=[
    dict(id='aleto',name='Aleto',file_import=True,approved_api=False,approved_web_collection=False,runner_connected=False,status='not_connected'),
    dict(id='avtopro',name='Avto.pro',file_import=False,approved_api=False,approved_web_collection=False,runner_connected=False,status='not_connected'),
    dict(id='file',name='CSV / дозволений експорт',file_import=True,approved_api=False,approved_web_collection=False,runner_connected=False,status='file_import_only'),
]


def overview(db):
    db.execute(text("SELECT set_config('statement_timeout','5000',true)"))
    sources=list(db.execute(select(CatalogueSource.id,CatalogueSource.name).order_by(CatalogueSource.name).limit(100)).mappings())
    latest=db.scalar(select(CatalogueJob).where(CatalogueJob.status=='applied').options(defer(CatalogueJob.rows),defer(CatalogueJob.resolutions)).order_by(CatalogueJob.applied_at.desc(),CatalogueJob.id).limit(1))
    prices=(latest.report.get('counts',{}).get('prices',{}).get('inserted')) if latest else None
    op_count=db.scalar(select(func.count()).select_from(CatalogueOperation).where(CatalogueOperation.status.in_(['queued','running'])))
    run_count=db.scalar(select(func.count()).select_from(CanonicalRun).where(CanonicalRun.status.in_(['queued','running'])))
    op=db.execute(select(CatalogueOperation.id,CatalogueOperation.kind,CatalogueOperation.status,CatalogueOperation.created_at,CatalogueOperation.progress,CatalogueOperation.error,CatalogueJob.filename).join(CatalogueJob).where(CatalogueOperation.status.in_(['queued','running'])).order_by(CatalogueOperation.created_at.desc(),CatalogueOperation.id).limit(1)).mappings().first()
    run=db.execute(select(CanonicalRun.id,CanonicalRun.mode,CanonicalRun.status,CanonicalRun.created_at,CanonicalRun.error).where(CanonicalRun.status.in_(['queued','running'])).order_by(CanonicalRun.created_at.desc(),CanonicalRun.id).limit(1)).mappings().first()
    tasks=[]
    if op:
        progress=op['progress'] or {};planning=progress.get('phase')=='planning'
        tasks.append(dict(id=op['id'],kind='import_'+op['kind'],status=op['status'],created_at=op['created_at'],filename=op['filename'],error=op['error'],processed=progress.get('done') if planning else None,total=progress.get('total') if planning and progress.get('total',0)>0 else None,unit='offer_groups' if planning else None,phase=progress.get('phase'),valid_records=None))
    if run:tasks.append(dict(id=run['id'],kind='canonical_'+run['mode'],status=run['status'],created_at=run['created_at'],filename=None,error=run['error'],processed=None,total=None,unit=None,phase=None,valid_records=None))
    return dict(source_count=db.scalar(select(func.count()).select_from(CatalogueSource)),sources=[dict(r) for r in sources],capabilities=SOURCES,
        last_import=dict(id=latest.id,filename=latest.filename,applied_at=latest.applied_at) if latest else None,
        new_price_observations_last_import=prices,active_operations=op_count+run_count,
        current_task=max(tasks,key=lambda t:t['created_at']) if tasks else None,
        catalogue=dict(with_prices=db.scalar(select(func.count()).select_from(CatalogueOffer).join(CataloguePrice,(CataloguePrice.offer_id==CatalogueOffer.id)&(CataloguePrice.observed_at==CatalogueOffer.observed_at)).where(CataloguePrice.price_uah.is_not(None)|CataloguePrice.price_usd.is_not(None))),offers=db.scalar(select(func.count()).select_from(CatalogueOffer)),with_oem=db.scalar(select(func.count()).select_from(CatalogueOffer).where(func.length(func.trim(CatalogueOffer.properties['oem'].as_string()))>0))),
        collection_history_available=False,online_collection_enabled=False)
