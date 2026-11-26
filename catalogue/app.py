"""Isolated, read-only CarPot Catalogue API. No Warehouse imports."""
import os
import secrets
from contextlib import contextmanager
from typing import Literal

import pymysql
from fastapi import Depends, FastAPI, Header, HTTPException, Query

from monitor import router as monitor_router

app = FastAPI(title="CarPot Catalogue", version="0.1.0", docs_url=None, redoc_url=None)
app.include_router(monitor_router)

def authorize(x_catalogue_key: str | None = Header(default=None)):
    expected = os.environ.get("CATALOGUE_API_KEY", "")
    if not expected or not x_catalogue_key or not secrets.compare_digest(x_catalogue_key, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

@contextmanager
def db():
    required = ["MYSQLHOST", "MYSQLPORT", "MYSQLUSER", "MYSQLPASSWORD", "MYSQLDATABASE"]
    if any(not os.environ.get(name) for name in required):
        raise HTTPException(status_code=503, detail="Catalogue database not configured")
    connection = pymysql.connect(
        host=os.environ["MYSQLHOST"],
        port=int(os.environ["MYSQLPORT"]),
        user=os.environ["MYSQLUSER"],
        password=os.environ["MYSQLPASSWORD"],
        database=os.environ["MYSQLDATABASE"],
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=10,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        yield connection
    finally:
        connection.close()

@app.get("/health")
def health():
    return {"status": "ok", "service": "carpot-catalogue"}

@app.get("/api/v1/parts", dependencies=[Depends(authorize)])
def search_parts(q: str = Query(min_length=2, max_length=64), limit: int = Query(default=20, ge=1, le=100)):
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT supplier_id, article_number, name_uk, name_source
               FROM catalogue_parts
               WHERE article_number LIKE %s OR name_uk LIKE %s OR name_source LIKE %s
               ORDER BY article_number LIMIT %s""",
            (pattern, pattern, pattern, limit),
        )
        return {"items": cur.fetchall()}

@app.get("/api/v1/oem", dependencies=[Depends(authorize)])
def search_oem(number: str = Query(min_length=2, max_length=64), limit: int = Query(default=50, ge=1, le=100)):
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT o.oem_number, o.oem_manufacturer_id, o.supplier_id,
                      o.article_number, p.name_uk, p.name_source
               FROM catalogue_oem o
               LEFT JOIN catalogue_parts p
                 ON p.supplier_id=o.supplier_id AND p.article_number=o.article_number
               WHERE o.oem_number=%s LIMIT %s""",
            (number, limit),
        )
        return {"items": cur.fetchall()}


@app.get("/api/v1/volvo/article", dependencies=[Depends(authorize)])
def volvo_article_lookup(
    supplier_id: int = Query(ge=1, le=65535),
    article_number: str = Query(min_length=1, max_length=32),
):
    """Read-only OEM enrichment by exact verified supplier ID + article key.

    Does not assert fitment, does not fetch images, and never creates stock.
    The supplier-to-brand mapping must be validated before Warehouse calls it.
    """
    article_number = article_number.strip()
    if not article_number or any(ch in article_number for ch in ("\x00", "\n", "\r")):
        raise HTTPException(422, detail="Invalid article number")
    with db() as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT supplier_id, article_number, name_uk, name_source
               FROM catalogue_parts
               WHERE supplier_id=%s AND article_number=%s AND BINARY article_number=BINARY %s
               LIMIT 1""",
            (supplier_id, article_number, article_number),
        )
        part = cur.fetchone()
        cur.execute(
            """SELECT oem_number
               FROM catalogue_oem
               WHERE supplier_id=%s AND article_number=%s AND BINARY article_number=BINARY %s
                 AND oem_manufacturer_id=120
               ORDER BY oem_number LIMIT 101""",
            (supplier_id, article_number, article_number),
        )
        rows = cur.fetchall()
        # Optional additive enrichment; the legacy OEM endpoint remains usable
        # before the Volvo integration tables have been explicitly created.
        try:
            cur.execute('SELECT name_source,observed_at FROM catalogue_suppliers WHERE supplier_id=%s',(supplier_id,))
            supplier=cur.fetchone()
        except pymysql.MySQLError:
            supplier=None
    return {
        "supplier_name": supplier['name_source'] if supplier else None,
        "observed_at": str(supplier['observed_at']) if supplier else None,
        "source": "carpot-catalogue",
        "vehicle_manufacturer": "Volvo",
        "vehicle_manufacturer_id": 120,
        "supplier_id": supplier_id,
        "article_number": article_number,
        "part": part,
        "oem_numbers": [row["oem_number"] for row in rows[:100]],
        "oem_numbers_truncated": len(rows) > 100,
        "fitment_verified": False,
        "vehicle_modification": None,
        "photo": None,
        "note": "OEM cross references do not prove compatibility with a given K-Type/VIN.",
    }

# Volvo integration snapshots are explicitly imported, never built on API startup.
import json
from volvo_contract import validate as validate_volvo, digest as volvo_digest, compact_plan, coverage_verified


def volvo_snapshot(car_id, snapshot_sha=None):
    try:
        with db() as conn, conn.cursor() as cur:
            if snapshot_sha:
                cur.execute('SELECT payload,sha256 FROM catalogue_volvo_versions WHERE car_id=%s AND sha256=%s', (car_id,snapshot_sha))
            else:
                cur.execute('SELECT payload,sha256 FROM catalogue_volvo_snapshots WHERE car_id=%s', (car_id,))
            row = cur.fetchone()
            if row is not None:
                parsed=json.loads(row['payload'])
                if parsed.get('schema') in ('carpot.volvo.plan.v2','carpot.vehicle.plan.v1'):
                    # The latest directory is compact; raw data is stored once per version.
                    cur.execute('SELECT payload,sha256 FROM catalogue_volvo_versions WHERE car_id=%s AND sha256=%s',(car_id,row['sha256']))
                    row=cur.fetchone()
                    if row is None:
                        raise HTTPException(503, 'Catalogue snapshot version is unavailable')
    except (pymysql.MySQLError,ValueError,TypeError):
        raise HTTPException(503, 'Volvo catalogue is not ready') from None
    if row is None:
        raise HTTPException(409 if snapshot_sha else 404, 'Pinned source snapshot unavailable' if snapshot_sha else 'Exact source modification not imported')
    try:
        payload = validate_volvo(json.loads(row['payload']))
        if payload['car_id'] != car_id or volvo_digest(payload) != row['sha256'] or (snapshot_sha and row['sha256']!=snapshot_sha):
            raise ValueError('Snapshot checksum')
    except (ValueError, TypeError, KeyError):
        raise HTTPException(503, 'Volvo catalogue validation failed') from None
    return payload, row['sha256']


@app.get('/api/v1/volvo/modifications', dependencies=[Depends(authorize)])
def volvo_modifications(model_id: int = Query(gt=0)):
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute('''SELECT car_id,payload,sha256 FROM catalogue_volvo_snapshots
                           WHERE model_id=%s ORDER BY car_id LIMIT 101''', (model_id,))
            rows = cur.fetchall()
    except pymysql.MySQLError:
        raise HTTPException(503, 'Volvo catalogue is not ready') from None
    if len(rows) > 100:
        raise HTTPException(409, 'Model directory needs pagination')
    items = []
    for r in rows:
        try:
            data,sha=volvo_snapshot(r['car_id'])
            if data['model_id'] != model_id:raise ValueError('Snapshot identity mismatch')
        except (ValueError, KeyError, TypeError):
            raise HTTPException(503, 'Volvo catalogue validation failed') from None
        items.append(dict(source_modification_id=data['car_id'], model_id=model_id,
            modification=data['modification'], coverage=data['coverage'], coverage_verified=coverage_verified(data),taxonomy_status=data.get('taxonomy_status','unreviewed'),
            specifications=data.get('details', {}).get('passanger_car_attributes', [])))
    return dict(source='carpot-catalogue', items=items, ktype_mapping_verified=False)


@app.get('/api/v1/volvo/modifications/{car_id}/coverage', dependencies=[Depends(authorize)])
def volvo_coverage(car_id: int):
    data, sha = volvo_snapshot(car_id)
    return dict(source='carpot-catalogue', source_modification_id=car_id,
        coverage=data['coverage'],coverage_verified=coverage_verified(data),taxonomy_status=data.get('taxonomy_status','unreviewed'),type_count=len(data['categories']),article_count=len(data['articles']),
        snapshot_sha=sha, observed_at=data['observed_at'], photos='metadata_only')


@app.get('/api/v1/volvo/modifications/{car_id}/plan', dependencies=[Depends(authorize)])
def volvo_plan(car_id: int):
    data, sha = volvo_snapshot(car_id)
    # Partial data is useful for review/enrichment, never disguised as full plan.
    compact=compact_plan(data,sha)
    return dict(payload=compact,sha256=volvo_digest(compact))


@app.get('/api/v1/volvo/modifications/{car_id}/categories', dependencies=[Depends(authorize)])
def volvo_categories(car_id: int):
    data, sha = volvo_snapshot(car_id)
    return dict(items=data['categories'], coverage=data['coverage'], snapshot_sha=sha)


def linked_article_oems(items, manufacturer_id):
    keys = {(item['supplier_id'], item['article_number']) for item in items}
    ordered = sorted(keys)
    if not ordered:
        return {}
    references = {}
    try:
        with db() as conn, conn.cursor() as cur:
            for offset in range(0, len(ordered), 100):
                batch = ordered[offset:offset+100]
                placeholders = ','.join(['(%s,%s)'] * len(batch))
                params = (manufacturer_id, *(value for key in batch for value in key))
                cur.execute(
                    f'''SELECT o.supplier_id,o.article_number,o.oem_number,s.name_source
                        FROM catalogue_oem o LEFT JOIN catalogue_suppliers s ON s.supplier_id=o.supplier_id
                        WHERE o.oem_manufacturer_id=%s AND (o.supplier_id,o.article_number) IN ({placeholders})
                        ORDER BY o.supplier_id,o.article_number,o.oem_number LIMIT 10001''',
                    params,
                )
                rows = cur.fetchall()
                if len(rows)>10000:
                    raise HTTPException(503, 'OEM cross-reference batch exceeds limit')
                for row in rows:
                    key = (row['supplier_id'], row['article_number'])
                    # MySQL can use a case-insensitive collation for the indexed lookup.
                    if key in batch:
                        group=references.setdefault(key, {'supplier':row['name_source'], 'oem':[]})
                        group['oem'].append(dict(
                            manufacturerId=manufacturer_id, OENbr=row['oem_number'],
                            source='catalogue_oem',
                        ))
    except pymysql.MySQLError:
        raise HTTPException(503, 'Catalogue OEM cross-references unavailable') from None
    return references


def enrich_linked_articles(data, keys):
    items = [data['articles'][k] for k in sorted(set(keys))]
    references = linked_article_oems(items, data['manufacturer_id'])
    enriched = []
    for item in items:
        imported = references.get((item['supplier_id'], item['article_number']), {})
        snapshot_oems = [{key.casefold():value for key,value in ref.items()}
                         for ref in item.get('oem', [])]
        snapshot_numbers = {(ref.get('manufacturerid'), ref.get('oenbr')) for ref in snapshot_oems}
        additions = [ref for ref in imported.get('oem', []) if (ref['manufacturerId'], ref['OENbr']) not in snapshot_numbers]
        supplier = item.get('supplier') or []
        if not supplier and imported.get('supplier'):
            supplier = [{'description':imported['supplier']}]
        enriched.append({**item, 'supplier':supplier, 'oem': [*item.get('oem', []), *additions]})
    return dict(zip(sorted(set(keys)), enriched))


@app.get('/api/v1/volvo/modifications/{car_id}/articles', dependencies=[Depends(authorize)])
def volvo_articles(car_id: int, product_id: int = Query(gt=0), snapshot_sha: str = Query(pattern=r'^[0-9a-f]{64}$')):
    data, sha = volvo_snapshot(car_id,snapshot_sha)
    category = next((r for r in data['categories'] if r['product_id'] == product_id), None)
    if category is None:
        raise HTTPException(404, 'Part type not present for this modification')
    enriched = enrich_linked_articles(data, category['articles'])
    return dict(items=[enriched[key] for key in category['articles']], snapshot_sha=sha,
                product_id=product_id, car_id=car_id, fitment='source_modification_link',
                vin_verified=False, photos='metadata_only')


@app.get('/api/v1/vehicles/{car_id}/article-batch', dependencies=[Depends(authorize)])
def vehicle_article_batch(car_id: int, product_id: list[int] = Query(min_length=1,max_length=12),
                          snapshot_sha: str = Query(pattern=r'^[0-9a-f]{64}$')):
    data, sha = volvo_snapshot(car_id,snapshot_sha)
    products = {row['product_id']:row['articles'] for row in data['categories']}
    if any(pid not in products for pid in product_id):
        raise HTTPException(404, 'Part type not present for this modification')
    selected = {pid:products[pid] for pid in product_id}
    keys = [key for linked in selected.values() for key in linked]
    if len(keys)>3000:
        raise HTTPException(413, 'Article batch too large')
    enriched = enrich_linked_articles(data, keys)
    return dict(car_id=car_id, snapshot_sha=sha, fitment='source_modification_link',
                vin_verified=False, items={pid:[enriched[key] for key in linked]
                                          for pid,linked in selected.items()})


@app.get('/api/v1/volvo/diagnostics', dependencies=[Depends(authorize)])
def volvo_diagnostics():
    try:
        with db() as conn, conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) AS unique_oem_links FROM catalogue_oem WHERE oem_manufacturer_id=120')
            counts=cur.fetchone()
            cur.execute('SELECT COUNT(*) AS imported_models FROM catalogue_models WHERE manufacturer_id=120')
            counts.update(cur.fetchone())
            cur.execute('SELECT coverage,COUNT(*) AS modifications FROM catalogue_volvo_snapshots GROUP BY coverage')
            counts['coverage']=cur.fetchall()
    except pymysql.MySQLError:
        raise HTTPException(503,'Volvo integration tables are not ready') from None
    return dict(source='carpot-catalogue',counts=counts,photos='metadata_only',vin_fitment_verified=False)


@app.get('/api/v1/vehicles/directory', dependencies=[Depends(authorize)])
def vehicle_directory(after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100), car_id: int | None = Query(None,gt=0),
                      model_id: int | None = Query(None,gt=0),
                      maker_key: str | None = Query(None,min_length=1,max_length=100),
                      model_key: list[str] | None = Query(None,max_length=2)):
    # Directory-only rows have no fitment graph and must never advertise readiness.
    try:
        with db() as conn, conn.cursor() as cur:
            filters=['s.car_id>%s']
            args=[after]
            if car_id is not None:
                filters.append('s.car_id=%s')
                args.append(car_id)
            if model_id is not None:
                filters.append('s.model_id=%s')
                args.append(model_id)
            if maker_key:
                filters.append("REGEXP_REPLACE(LOWER(f.name_source),'[^[:alnum:]]','')=%s")
                args.append(maker_key)
            if model_key:
                # TecDoc source names carry platform identifiers in parentheses:
                # "XC60 II (246)" must match lookup key "xc60ii", without
                # treating the platform number as a different car generation.
                filters.append("REGEXP_REPLACE(REGEXP_REPLACE(LOWER(m.name_source),'[(][^)]*[)]',''),'[^[:alnum:]]','') IN ("+
                               ','.join(['%s']*len(model_key))+')')
                args.extend(model_key)
            cur.execute("""SELECT s.car_id,s.model_id AS source_model_id,m.manufacturer_id,m.name_source AS model_name,
                f.name_source AS manufacturer_name FROM catalogue_volvo_snapshots s
                JOIN catalogue_models m ON m.id=s.model_id
                JOIN catalogue_manufacturers f ON f.id=m.manufacturer_id
                WHERE """+' AND '.join(filters)+' ORDER BY s.car_id LIMIT %s',(*args,limit+1))
            rows=cur.fetchall()
    except pymysql.MySQLError:
        raise HTTPException(503,'Vehicle catalogue unavailable') from None
    items=[]
    for row in rows[:limit]:
        try:
            data,sha=volvo_snapshot(row['car_id'])
        except HTTPException:
            continue # Corrupt/missing pinned graph is not a usable modification.
        linked={key for r in data['categories'] for key in r.get('articles',[])}
        if not linked or data['manufacturer_id']!=row['manufacturer_id'] or data['model_id']!=row['source_model_id'] or not row['manufacturer_name'] or not row['model_name']:
            continue
        model=data.get('model') or {}
        generation=model.get('generation') or None
        items.append(dict(source_modification_id=data['car_id'],model_id=data['model_id'],
            manufacturer_id=data['manufacturer_id'],manufacturer=row['manufacturer_name'],model=row['model_name'],
            generation=generation,modification=data['modification'],coverage=data['coverage'],
            type_count=len(data['categories']),article_count=len(linked),
            oem_links=sum(len(data['articles'][key].get('oem',[])) for key in linked),snapshot_sha=sha,
            specifications=data.get('details',{}).get('passanger_car_attributes',[])))
    return dict(items=items,next_after=rows[limit-1]['car_id'] if len(rows)>limit else None)


@app.get('/api/v1/vehicles/source-graph', dependencies=[Depends(authorize)])
def vehicle_source_graph(
    kind: Literal["passenger", "commercial"],
    manufacturer_id: int = Query(gt=0),
    model_id: int = Query(gt=0),
    car_id: int = Query(gt=0),
):
    """One exact Oracle identity, with explicit availability and provenance."""
    identity = dict(kind=kind, manufacturer_id=manufacturer_id, model_id=model_id, car_id=car_id)
    live_enabled = (os.getenv("RAILWAY_ENVIRONMENT_NAME") == "catalogue-staging"
                    and os.getenv("ORACLE_CATALOGUE_ENABLED", "false").lower() == "true")
    if live_enabled:
        from oracle_source_graph import live_graph
        try:
            return live_graph(identity)
        except HTTPException as error:
            if error.status_code != 503 or kind != "passenger":
                raise
            cached = published_source_graph(identity)
            if cached["status"] == "available":
                return cached
            raise error
    return published_source_graph(identity)


def published_source_graph(identity):
    kind, manufacturer_id, model_id, car_id = (identity[field] for field in
                                                ("kind", "manufacturer_id", "model_id", "car_id"))
    # Older Catalogue deployments can still serve a published passenger graph.
    if kind != "passenger":
        return dict(identity=identity, status="unsupported", reason="namespace_not_published")
    try:
        data, snapshot_sha = volvo_snapshot(car_id)
    except HTTPException as error:
        if error.status_code == 404:
            return dict(identity=identity, status="absent", reason="snapshot_not_published")
        raise
    if (data["manufacturer_id"], data["model_id"], data["car_id"]) != (manufacturer_id, model_id, car_id):
        return dict(identity=identity, status="identity_mismatch", reason="snapshot_identity_mismatch")
    if data.get("source_scope") != "passenger_prd_article_oem":
        return dict(identity=identity, status="unverified", reason="source_scope_unverified")
    plan = compact_plan(data, snapshot_sha)
    if not any(row.get("source_fitment_linked") and row["article_count"] > 0 for row in plan["categories"]):
        return dict(identity=identity, status="unverified", reason="no_linked_prd_articles")
    return dict(identity=identity, status="available", source_scope=data["source_scope"],
                plan=dict(payload=plan, sha256=volvo_digest(plan)))


@app.get('/api/v1/vehicles/{car_id}/plan', dependencies=[Depends(authorize)])
def vehicle_plan(car_id: int):
    return volvo_plan(car_id)


@app.get('/api/v1/vehicles/{car_id}/articles', dependencies=[Depends(authorize)])
def vehicle_articles(car_id: int, product_id: int = Query(gt=0), snapshot_sha: str = Query(pattern=r'^[0-9a-f]{64}$')):
    return volvo_articles(car_id,product_id,snapshot_sha)


@app.get('/api/v1/articles/oem',dependencies=[Depends(authorize)])
def exact_article_oem(manufacturer:str=Query(min_length=1,max_length=100),
                      supplier_brand:str=Query(min_length=1,max_length=128),
                      article_number:str=Query(min_length=1,max_length=32),
                      supplier_id:int|None=Query(None,ge=1,le=65535)):
    """All makes: exact article and supplier, filtered by exact vehicle manufacturer.
    Only SELECT; ambiguous identities are unavailable, never guessed.
    """
    import unicodedata
    norm=lambda s:unicodedata.normalize('NFKC',s or '').strip().casefold()
    if not manufacturer.strip() or not supplier_brand.strip() or not article_number.strip():raise HTTPException(422,'Empty identity')
    if any(c in article_number for c in ('\x00','\n','\r')):raise HTTPException(422,'Invalid article number')
    with db() as conn,conn.cursor() as cur:
        cur.execute("""SELECT id,name_source FROM catalogue_manufacturers
            WHERE LOWER(TRIM(name_source))=LOWER(TRIM(%s)) LIMIT 100""",(manufacturer,))
        makers=[m for m in cur.fetchall() if norm(m['name_source'])==norm(manufacturer)]
        if len(makers)!=1:raise HTTPException(404,'Manufacturer identity unavailable')
        make=makers[0]
        cur.execute("""SELECT p.supplier_id,p.article_number,s.name_source AS supplier_name
            FROM catalogue_parts p JOIN catalogue_suppliers s ON s.supplier_id=p.supplier_id
            WHERE p.article_number=%s AND BINARY p.article_number=BINARY %s
              AND LOWER(TRIM(s.name_source))=LOWER(TRIM(%s))
              AND (%s IS NULL OR p.supplier_id=%s) LIMIT 100""",
            (article_number,article_number,supplier_brand,supplier_id,supplier_id))
        articles=[a for a in cur.fetchall() if a['article_number']==article_number and norm(a['supplier_name'])==norm(supplier_brand)]
        if len(articles)!=1:raise HTTPException(404,'Supplier article identity unavailable')
        article=articles[0]
        cur.execute("""SELECT oem_number FROM catalogue_oem
            WHERE supplier_id=%s AND article_number=%s AND BINARY article_number=BINARY %s
              AND oem_manufacturer_id=%s ORDER BY oem_number LIMIT 1001""",
            (article['supplier_id'],article_number,article_number,make['id']))
        rows=cur.fetchall()
    if len(rows)>1000:raise HTTPException(409,'Too many references for exact article')
    return dict(manufacturer=make['name_source'],manufacturer_id=make['id'],
        supplier_id=article['supplier_id'],supplier_name=article['supplier_name'],
        article_number=article_number,oem_numbers=[r['oem_number'] for r in rows],vin_verified=False)


# Additive, feature-disabled-by-default Oracle preview routes. No Warehouse writes.
from oracle_gateway import build_router as build_oracle_gateway_router
app.include_router(build_oracle_gateway_router(authorize))
