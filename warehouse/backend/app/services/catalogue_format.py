"""CarPot Catalogue Import v2; bounded, offline parsing with a v1 adapter."""
import csv
import gzip
import hashlib
import io
import json
import re
import stat
import sqlite3
import tempfile
import zipfile
import zlib
from pathlib import Path
from typing import Annotated
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator
from app.services.aleto_import import load_package, money, source_url, observation, DICTIONARY, CATEGORY_ALIASES, CATEGORIES, identity

VerbatimString = Annotated[str, StringConstraints(strip_whitespace=False)]

MAX_UPLOAD = 16 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_ROWS = 50000
MAX_RATIO = 100
REQUIRED = {'schema_version','source','source_article','manufacturer','model','category','subcategory','part_name','source_url','observed_at'}
OPTIONAL = {'generation','year_from','year_to','oem','condition','price_uah','price_usd','side','position','source_record'}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class ImportRow(BaseModel):
    model_config = ConfigDict(extra='forbid',str_strip_whitespace=True)
    schema_version: str = '2'
    source: str = Field(min_length=1,max_length=100,pattern=r'^[a-z0-9][a-z0-9._-]*$')
    source_article: str = Field(min_length=1,max_length=150)
    manufacturer: str = Field(min_length=1,max_length=100)
    model: str = Field(min_length=1,max_length=100)
    generation: str = Field(default='',max_length=100)
    year_from: int | None = Field(default=None,ge=1886,le=2100)
    year_to: int | None = Field(default=None,ge=1886,le=2100)
    category: str = Field(min_length=1,max_length=200)
    subcategory: str = Field(min_length=1,max_length=200)
    part_name: str = Field(min_length=1,max_length=1000)
    oem: str = Field(default='',max_length=1000)
    condition: str = Field(default='',max_length=200)
    side: str = Field(default='',max_length=100)
    position: str = Field(default='',max_length=100)
    price_uah: str | None = None
    price_usd: str | None = None
    source_url: str = Field(max_length=2000)
    observed_at: str
    source_record: dict[VerbatimString,VerbatimString] = Field(default_factory=dict,max_length=128)

    @field_validator('source_record',mode='before')
    @classmethod
    def provenance(cls,value):
        if value in ('',None):return {}
        if isinstance(value,str):
            if len(value.encode())>16384:raise ValueError('Source record exceeds 16 KiB')
            try:value=json.loads(value)
            except (json.JSONDecodeError,RecursionError):raise ValueError('Invalid source_record JSON') from None
        if not isinstance(value,dict) or any(not isinstance(k,str) or not isinstance(v,str) or len(k)>128 or len(v)>4096 for k,v in value.items()):
            raise ValueError('Source record must preserve string fields only')
        if len(json.dumps(value,ensure_ascii=False).encode())>16384:raise ValueError('Source record exceeds 16 KiB')
        return value

    @field_validator('year_from','year_to',mode='before')
    @classmethod
    def blank_year(cls,value):
        if value in ('',None):return None
        if isinstance(value,bool) or not re.fullmatch(r'\d{4}',str(value)):raise ValueError('Invalid year')
        return value

    @field_validator('price_uah','price_usd',mode='before')
    @classmethod
    def price(cls,value):
        result=money(value)
        return str(result.quantize(Decimal('.01'))) if result is not None else None

    @field_validator('observed_at')
    @classmethod
    def timestamp(cls,value):
        return observation(value).isoformat()

    @model_validator(mode='after')
    def valid(self):
        if self.schema_version!='2':raise ValueError('Expected schema_version=2')
        if self.year_from and self.year_to and self.year_from>self.year_to:raise ValueError('Invalid year range')
        from urllib.parse import urlsplit
        parsed=urlsplit(self.source_url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443):raise ValueError('Expected HTTPS source URL without credentials')
        if self.source=='aleto':source_url(self.source_url)
        if any(ord(c)<32 for name in ('source_article','manufacturer','model','generation','category','subcategory','part_name','oem','condition','side','position','source_url') for c in getattr(self,name)):raise ValueError('Control characters in name')
        return self



def legacy_provenance(row):
    record=row.get('source_record') or {}
    if row['source']!='aleto' or not record:return row
    if 'article' in record and record['article'].strip()!=row['source_article']:
        raise ValueError('Source record article mismatch')
    category=record.get('category_source',record.get('category'))
    subcategory=record.get('subcategory_raw',record.get('subcategory'))
    if category is not None:
        row['_raw_category']=category
        known=CATEGORY_ALIASES.get(category,category)
        if known not in CATEGORIES or identity(known)!=identity(row['category']):row['_review_category']=True
    if subcategory is not None:
        row['_raw_subcategory']=subcategory
        known=DICTIONARY.get(subcategory)
        if not known or identity(known)!=identity(row['subcategory']):row['_review_subcategory']=True
    return row


def parse_csv(raw):
    if len(raw)>MAX_EXPANDED:raise ValueError('CSV exceeds expanded size limit')
    try:
        content=raw.decode('utf-8-sig')
    except UnicodeError:raise ValueError('CSV must be UTF-8') from None
    csv.field_size_limit(16384)
    reader=csv.DictReader(io.StringIO(content,newline=''),strict=True)
    columns=reader.fieldnames or []
    if len(set(columns))!=len(columns) or not REQUIRED<=set(columns) or set(columns)-REQUIRED-OPTIONAL:
        raise ValueError('Invalid, missing or duplicate CSV columns; see Import v2 schema')
    rows=[]
    try:
        for index,row in enumerate(reader,2):
            if index>MAX_ROWS+1:raise ValueError('Too many rows')
            if None in row or any(v is None for v in row.values()):raise ValueError(f'CSV row {index}: wrong field count')
            try: rows.append(legacy_provenance(ImportRow.model_validate(row).model_dump()))
            except ValueError:raise ValueError(f'CSV row {index}: invalid field, price, date or URL') from None
    except csv.Error:raise ValueError('Malformed CSV') from None
    if not rows:raise ValueError('CSV is empty')
    return rows


def parse_upload(raw, filename):
    if not raw or len(raw)>MAX_UPLOAD:raise ValueError('File must be 1 byte to 16 MiB')
    if raw.startswith(b'PK'):
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                entries=archive.infolist()
                names=[e.filename for e in entries]
                if len(entries)!=2 or len(set(names))!=2 or 'manifest.json' not in names:raise ValueError('ZIP must contain only manifest.json and one root CSV')
                for e in entries:
                    if '/' in e.filename or '\\' in e.filename or ':' in e.filename or any(ord(c)<32 for c in e.filename) or len(e.filename)>200 or e.filename in ('.','..') or e.flag_bits&1 or stat.S_ISLNK(e.external_attr>>16):raise ValueError('Unsafe ZIP entry')
                    if e.file_size>MAX_EXPANDED or e.file_size>MAX_RATIO*max(e.compress_size,1):raise ValueError('ZIP size/ratio limit exceeded')
                if sum(e.file_size for e in entries)>MAX_EXPANDED or archive.getinfo('manifest.json').file_size>16384:raise ValueError('Expanded ZIP exceeds limit')
                manifest=json.loads(archive.read('manifest.json'))
                if set(manifest)!={'schema_version','file','sha256'} or manifest['schema_version']!=2:raise ValueError('Unsupported ZIP manifest')
                name=manifest['file']
                if not isinstance(name,str) or not name.endswith('.csv') or set(names)!={'manifest.json',name}:raise ValueError('Manifest CSV mismatch')
                data=archive.read(name)
                if hashlib.sha256(data).hexdigest()!=manifest['sha256']:raise ValueError('CSV SHA-256 mismatch')
                return parse_csv(data),'v2-zip'
        except (zipfile.BadZipFile,KeyError,TypeError,NotImplementedError,OSError,zlib.error,RecursionError,json.JSONDecodeError):raise ValueError('Invalid ZIP/manifest') from None
    if raw.startswith(b'SQLite format 3\x00') or raw.startswith(b'\x1f\x8b'):
        if raw.startswith(b'\x1f\x8b'):
            try:
                with gzip.GzipFile(fileobj=io.BytesIO(raw)) as c: expanded=c.read(MAX_EXPANDED+1)
            except (OSError,EOFError,zlib.error):raise ValueError('Corrupt gzip') from None
            if len(expanded)>MAX_EXPANDED or len(expanded)>MAX_RATIO*len(raw):raise ValueError('Gzip size/ratio limit exceeded')
        else:expanded=raw
        with tempfile.TemporaryDirectory(prefix='catalogue-v1-') as directory:
            path=Path(directory)/'legacy.sqlite3';path.write_bytes(expanded)
            with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
                conn.execute('PRAGMA query_only=ON')
                objects=conn.execute("SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view','trigger')").fetchall()
                allowed={'offers','applications','taxonomy_paths','metadata'}
                if any(kind!='table' or name not in allowed or not sql.upper().startswith('CREATE TABLE') for name,kind,sql in objects):
                    raise ValueError('Legacy SQLite may contain only ordinary staging tables, no views/triggers/code')
                if not {'offers','applications','taxonomy_paths'}<={name for name,_,_ in objects}:raise ValueError('Missing legacy staging tables')
                for table in ('offers','applications','taxonomy_paths'):
                    if conn.execute('SELECT count(*) FROM '+table).fetchone()[0]>MAX_ROWS:raise ValueError('Too many legacy rows')
            legacy=load_package(path)
        offers={r['article']:r for r in legacy['offers']}
        rows=[]
        for path in legacy['paths']:
            offer=offers[path['article']]
            brand,model=path['model'].split(' ',1)
            row=ImportRow(source='aleto',source_article=offer['article'],manufacturer=brand,model=model,
                category=path['category'],subcategory=DICTIONARY.get(path['raw_subcategory']) or path['raw_subcategory'],
                part_name=offer['title'],oem=offer['oem'] or '',condition=offer['condition'],
                price_uah=str(offer['price_uah']) if offer['price_uah'] is not None else None,
                price_usd=str(offer['price_usd']) if offer['price_usd'] is not None else None,
                source_url=offer['url'],observed_at=offer['observed_at'].isoformat()).model_dump()
            row['_raw_category']=path['raw_category'];row['_raw_subcategory']=path['raw_subcategory']
            if not DICTIONARY.get(path['raw_subcategory']):row['_review_subcategory']=True
            rows.append(row)
        return rows,'aleto-v1'
    return parse_csv(raw),'v2-csv'
