"""Separate route prefix avoids /parts/{id}; the legacy /parts is unchanged."""
from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.api.routes import DB, Auth
from app.search.service import search, REVISION, FEATURES
router=APIRouter(prefix='/api/v1/smart-search',tags=['Smart parts search'])

@router.get('/readiness')
def readiness(db:DB,who:Auth):
    from app.staging import migration_heads
    try:
        versions=frozenset(db.execute(text('SELECT version_num FROM alembic_version')).scalars())
        if versions!=migration_heads() or REVISION not in versions:raise HTTPException(503,'Smart Search schema is not ready')
        if not db.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname='pg_trgm')")):raise HTTPException(503,'pg_trgm is not ready')
        for name in ('ix_parts_smart_fts','ix_parts_smart_trgm','ix_parts_smart_oem_number','ix_parts_smart_article_number','ix_vehicle_smart_model','ix_vehicle_smart_brand'):
            if not db.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_index WHERE indexrelid=to_regclass(:name) AND indisvalid)'),{'name':name}):raise HTTPException(503,'Smart Search indexes are not ready')
        db.execute(text("SELECT warehouse_search_text('Перевірка'),warehouse_search_code('A-01')"))
    except SQLAlchemyError:raise HTTPException(503,'Smart Search is unavailable') from None
    return {'status':'ready','contract_version':8,'required_revision':REVISION,'database_revisions':sorted(versions),'features':FEATURES}

@router.get('/parts')
def parts(db:DB,who:Auth,q:str=Query('',max_length=160),vehicle_id:str|None=Query(None,max_length=36),
          manufacturer:str|None=Query(None,max_length=100),model:str|None=Query(None,max_length=100),
          in_stock:bool=False,offset:int=Query(0,ge=0,le=100000),limit:int=Query(50,ge=1,le=100)):
    return search(db,who.user.id,q=q,vehicle_id=vehicle_id,manufacturer=manufacturer,model=model,in_stock=in_stock,offset=offset,limit=limit)
