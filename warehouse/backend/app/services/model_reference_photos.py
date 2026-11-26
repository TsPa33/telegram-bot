"""Optional model-only cutout library. No writes to Warehouse business DB.

Provider contract is operator-approved, not an implemented commercial provider.
Only model identity is sent. Never send VIN, donor, tenant or user identifiers.
"""
import base64
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import unicodedata
from urllib.parse import urlsplit
from contextlib import contextmanager

LOG = logging.getLogger(__name__)
MAX_IMAGE = 2_000_000
MAX_RESPONSE = 3_000_000
DAILY_LIMIT = 12
MAX_ATTEMPTS = 3

def clean(value):
    if not isinstance(value, str):
        return ""
    value = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    if len(value) > 100 or any(not (c.isalnum() or c in " -_()./+&") for c in value):
        return ""
    return value

def model_identity(make, model, generation, year):
    make, model, generation = clean(make), clean(model), clean(generation)
    if not make or not model or (year is not None and (type(year) is not int or not 1886 <= year <= 2100)):
        return None
    return {"manufacturer": make, "model": model, "generation": generation, "year": year}

def key_for(identity):
    return hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def row_identity(row):
    return model_identity(row.manufacturer, row.model, row.generation, row.year)

def library_path():
    # Fail closed; deployment must explicitly mount a dedicated durable directory.
    if os.getenv("WAREHOUSE_ENV") != "staging" or os.getenv("WAREHOUSE_MODEL_PHOTO_ENABLED") != "true":
        return None
    directory = os.getenv("WAREHOUSE_MODEL_PHOTO_DIR")
    if not directory or not Path(directory).is_absolute() or not Path(directory).is_dir():
        return None
    return Path(directory) / "model-cutouts-v1.sqlite3"

@contextmanager
def connect(path, read_only=False):
    db = sqlite3.connect(path.resolve().as_uri()+"?mode=ro" if read_only else path, uri=read_only, timeout=1)
    db.row_factory = sqlite3.Row
    try:
        yield db
        if not read_only: db.commit()
    except Exception:
        if not read_only: db.rollback()
        raise
    finally:
        db.close()

def init(path):
    with connect(path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS photos(
          key TEXT PRIMARY KEY, identity TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
          attempts INTEGER NOT NULL DEFAULT 0, next_try INTEGER NOT NULL DEFAULT 0,
          image BLOB, attribution TEXT, source_url TEXT, license_url TEXT, license TEXT);
        CREATE TABLE IF NOT EXISTS daily_attempts(day INTEGER PRIMARY KEY, count INTEGER NOT NULL);
        """)

def enqueue(path, identities):
    rows = [(key_for(i),json.dumps(i,ensure_ascii=False,sort_keys=True)) for i in identities if i]
    with connect(path) as db:
        db.executemany("INSERT OR IGNORE INTO photos(key,identity) VALUES (?,?)", rows)

def claim(path, now):
    # Claim before external work: persistent rate limit and retry ceiling, even across restarts.
    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        day = int(now)//86400
        count = db.execute("SELECT count FROM daily_attempts WHERE day=?", (day,)).fetchone()
        if count and count[0]>=DAILY_LIMIT: return None
        row = db.execute("SELECT * FROM photos WHERE state='pending' AND attempts<? AND next_try<=? ORDER BY attempts,key LIMIT 1",(MAX_ATTEMPTS,int(now))).fetchone()
        if not row:return None
        db.execute("UPDATE photos SET attempts=attempts+1,next_try=? WHERE key=?", (int(now)+21600,row["key"]))
        db.execute("INSERT INTO daily_attempts VALUES (?,1) ON CONFLICT(day) DO UPDATE SET count=count+1",(day,))
        return dict(row)

def https_url(value):
    if not isinstance(value,str) or len(value)>1500: return False
    try:
        p=urlsplit(value)
        return p.scheme=="https" and bool(p.hostname) and not p.username and not p.password
    except ValueError: return False

def prepare_cutout(raw):
    from PIL import Image, ImageOps
    if not raw or len(raw)>MAX_IMAGE: raise ValueError("image size")
    with Image.open(io.BytesIO(raw)) as im:
        if im.format not in ("PNG","WEBP") or im.width*im.height>4_000_000 or getattr(im,"n_frames",1)!=1:
            raise ValueError("unsupported image")
        if im.mode not in ("RGBA","LA") and "transparency" not in im.info:
            raise ValueError("alpha required")
        cutout=ImageOps.exif_transpose(im).convert("RGBA")
        alpha=cutout.getchannel("A")
        histogram=alpha.histogram()
        pixels=cutout.width*cutout.height
        if histogram[0]<pixels*0.08 or sum(histogram[230:])<pixels*0.15:
            raise ValueError("not a usable transparent cutout")
        box=alpha.getbbox()
        if not box: raise ValueError("empty cutout")
        cutout=cutout.crop(box)
        cutout.thumbnail((640,400))
        # Transparent padding, never paint the card background into the image.
        padded=Image.new("RGBA",(cutout.width+12,cutout.height+12))
        padded.alpha_composite(cutout,(6,6))
        out=io.BytesIO()
        padded.save(out,"WEBP",quality=80,method=4)
        data=out.getvalue()
        if len(data)>150_000: raise ValueError("optimized image too large")
        return data

def validate_result(identity, result):
    # Provider must be contracted to supply actual licensed, identity-reviewed cutouts.
    # Its claims still require live provider acceptance; not independent visual verification.
    if result.get("identity")!=identity or result.get("kind")!="real_photo" or result.get("commercial_use") is not True or result.get("derivatives_allowed") is not True or result.get("identity_reviewed") is not True:
        raise ValueError("unapproved photo")
    if not https_url(result.get("source_url")) or not https_url(result.get("license_url")):
        raise ValueError("missing source or license")
    for field in ("attribution","license"):
        if not isinstance(result.get(field),str) or not 0<len(result[field].strip())<=240:
            raise ValueError("missing credit")
    raw=base64.b64decode(result["image_base64"],validate=True)
    return prepare_cutout(raw)

def provider_settings():
    url=os.getenv("WAREHOUSE_MODEL_PHOTO_PROVIDER_URL","")
    token=os.getenv("WAREHOUSE_MODEL_PHOTO_PROVIDER_TOKEN","")
    if os.getenv("WAREHOUSE_MODEL_PHOTO_PROVIDER_APPROVED")!="true" or not https_url(url) or not token:
        return None
    return url,token

def fetch_photo(settings, identity):
    import httpx
    url,token=settings
    with httpx.Client(timeout=httpx.Timeout(20.0,connect=5.0),follow_redirects=False,trust_env=False) as client:
        with client.stream("POST",url,json=identity,headers={"Authorization":"Bearer "+token,"Accept":"application/json"}) as response:
            response.raise_for_status()
            raw=bytearray()
            for chunk in response.iter_bytes():
                raw.extend(chunk)
                if len(raw)>MAX_RESPONSE: raise ValueError("response too large")
    return json.loads(raw)

def process_one(path, settings, now=None, fetch=fetch_photo):
    if not settings:return False
    row=claim(path,time.time() if now is None else now)
    if not row:return False
    try:
        identity=json.loads(row["identity"])
        result=fetch(settings,identity)
        image=validate_result(identity,result)
        with connect(path) as db:
            db.execute("UPDATE photos SET state='ready',image=?,attribution=?,source_url=?,license_url=?,license=? WHERE key=?",
                       (image,result["attribution"],result["source_url"],result["license_url"],result["license"],row["key"]))
    except Exception:
        # Do not log URLs, provider bodies, tokens or customer-entered labels.
        LOG.warning("model cutout request failed; bounded retry policy applies")
    return True

def read_metadata(rows):
    path=library_path()
    if not path or not path.is_file(): return {}
    keys={row.id:key_for(i) for row in rows if (i:=row_identity(row))}
    if not keys:return {}
    try:
        with connect(path,True) as db:
            values=list(set(keys.values()))
            hits={r["key"]:dict(r) for r in db.execute(
                "SELECT key,attribution,source_url,license_url,license FROM photos WHERE state='ready' AND key IN ("+",".join("?" for _ in values)+")",values)}
        return {id:{"url":"/api/v1/vehicle-photos/reference/"+key,**{k:v for k,v in hits[key].items() if k!="key"}} for id,key in keys.items() if key in hits}
    except (OSError,sqlite3.Error):
        return {}

def read_image(key):
    path=library_path()
    if not path or not path.is_file() or not re.fullmatch("[a-f0-9]{64}",key):return None
    try:
        with connect(path,True) as db:
            row=db.execute("SELECT image FROM photos WHERE key=? AND state='ready'",(key,)).fetchone()
            return row[0] if row else None
    except (OSError,sqlite3.Error):
        return None

def scan_page(path, after):
    from sqlalchemy import select, text
    from app.db import engine
    from app.models import Vehicle
    # Only committed active donor model fields. No inventory writes, no VIN query.
    with engine().connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SET LOCAL statement_timeout = '3s'"))
        stmt=select(Vehicle.id,Vehicle.manufacturer,Vehicle.model,Vehicle.generation,Vehicle.year).where(Vehicle.archived.is_(False))
        if after:stmt=stmt.where(Vehicle.id>after)
        rows=conn.execute(stmt.order_by(Vehicle.id).limit(100)).all()
    enqueue(path,[row_identity(r) for r in rows])
    return rows[-1].id if len(rows)==100 else ""

def start_worker():
    stop=threading.Event()
    path=library_path()
    if not path:return stop,None
    def loop():
        # Linux/Railway singleton lock; never spawn duplicate providers on same volume.
        import fcntl
        try:
            with open(path.with_suffix(".lock"),"a") as lock:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:return
                init(path)
                cursor=""
                while not stop.is_set():
                    try:
                        cursor=scan_page(path,cursor)
                        if not stop.is_set():process_one(path,provider_settings())
                    except Exception:LOG.warning("model cutout scan unavailable")
                    stop.wait(60 if cursor else 120)
        except Exception:LOG.warning("model cutout library unavailable")
    thread=threading.Thread(target=loop,name="model-cutout-library",daemon=True)
    thread.start()
    return stop,thread
