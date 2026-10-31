"""Parse legacy CP1251 / converted JSONL.gz vehicle references without modifying donors."""
import gzip
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.vehicle_directory import VehicleDirectoryVariant, VehicleDirectoryImport

MAX_UPLOAD = 16 * 1024 * 1024
MAX_PLAIN = 24 * 1024 * 1024
MAX_ROWS = 40000
YEARS = re.compile(r'\[\s*(\d{4})\s*-\s*(\d{4}|NULL)\s*\]')
POWER = re.compile(r'\[(\d+)\s*(kW|PS)\]')
BRACKETS = re.compile(r'\[([^]]*)\]')
FUELS = {'petrol':'Бензин','diesel':'Дизель','electric':'Електро','hybrid':'Гібрид','lpg':'Газ','cng':'Газ'}

def brackets(value):
    return list(dict.fromkeys(v.strip() for v in BRACKETS.findall(value or '') if v.strip()))

def trim(text_value, size):
    value = str(text_value or '').strip()
    if len(value)>size:
        raise HTTPException(422, 'Занадто довга назва в каталозі')
    return value

def parse_legacy(data: str):
    brand = model = None
    current = None
    def finish(row):
        if row is None: return None
        fields = row.pop('fields')
        years = YEARS.search(fields.get('Год',''))
        power = dict((unit, int(value)) for value,unit in POWER.findall(fields.get('Мощность','')))
        def num(k):
            try: return Decimal(fields[k].replace(',','.'))
            except (KeyError, InvalidOperation): return None
        def drive(s):
            value=s.casefold()
            if 'все колеса' in value or 'всі колеса' in value:return 'AWD'
            if 'передни' in value:return 'FWD'
            if 'задни' in value:return 'RWD'
            return None
        return {**row,'year_from':int(years[1]) if years else None,
            'year_to':int(years[2]) if years and years[2]!='NULL' else None,
            'displacement_l':num('Обьем'),
            'fuel_type':FUELS.get((fields.get('Топливо') or fields.get('Двигатель') or '').lower()),
            'power_kw':power.get('kW'),'power_ps':power.get('PS'),
            'body':(brackets(fields.get('Кузов')) or [None])[0],
            'drive_type':drive(fields.get('Привод','')),
            'engine_codes':brackets(fields.get('Код двигателя')),
            'kba_numbers':brackets(fields.get('KBA Number'))}
    for line in data.splitlines():
        level=len(line)-len(line.lstrip('\t'))
        value=line.lstrip('\t').strip()
        if not value: continue
        if level==1:
            if current:yield finish(current);current=None
            brand=value;model=None
        elif level==2:
            if current:yield finish(current);current=None
            model=value
        elif level==3 and brand and model:
            if current:yield finish(current)
            current={'brand':brand,'model':model,'modification':value,'fields':{}}
        elif level==4 and current and '=' in value:
            k,v=value.split('=',1);current['fields'][k.strip()]=v.strip()
    if current:yield finish(current)

def parse_upload(raw: bytes, filename: str):
    if len(raw)>MAX_UPLOAD:raise HTTPException(413,'Файл перевищує 16 МБ')
    if not raw:raise HTTPException(422,'Порожній файл')
    lower=filename.lower()
    if lower.endswith('.jsonl.gz'):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as z:
            data=z.read(MAX_PLAIN+1)
        if len(data)>MAX_PLAIN:raise HTTPException(413,'Розпакований файл завеликий')
        try:
            rows=(json.loads(line) for line in data.decode('utf-8').splitlines() if line.strip())
            for row in rows:
                yield {'brand':row['brand'],'model':row['model'],'modification':row['modification'],
                    'year_from':row.get('year_from'),'year_to':row.get('year_to'),
                    'displacement_l':row.get('displacement_l'),'fuel_type':row.get('fuel'),
                    'power_kw':row.get('power_kw'),'power_ps':row.get('power_ps'),
                    'body':row.get('body'),'drive_type':row.get('drive'),
                    'engine_codes':row.get('engine_codes') or [],'kba_numbers':row.get('kba_numbers') or []}
        except (KeyError,ValueError,TypeError,UnicodeDecodeError) as exc:
            raise HTTPException(422,'Некоректний нормалізований JSONL') from exc
    elif lower.endswith('.txt'):
        try: decoded=raw.decode('cp1251')
        except UnicodeDecodeError as exc:raise HTTPException(422,'Не вдалося прочитати Windows-1251') from exc
        yield from parse_legacy(decoded)
    else:raise HTTPException(415,'Підтримуються .txt у Windows-1251 або .jsonl.gz')

def validated(row):
    brand=trim(row.get('brand'),120); model=trim(row.get('model'),200)
    modification=trim(row.get('modification'),350)
    if not brand or not model or not modification:raise HTTPException(422,'Відсутня марка, модель або модифікація')
    start=row.get('year_from');end=row.get('year_to')
    if start is not None:start=int(start)
    if end is not None:end=int(end)
    if start is not None and not 1886<=start<=2100:raise HTTPException(422,'Некоректний початковий рік')
    if end is not None and (start is None or not start<=end<=2100):raise HTTPException(422,'Некоректний кінцевий рік')
    displacement=row.get('displacement_l')
    if displacement is not None:
        displacement=Decimal(str(displacement)).quantize(Decimal('0.1'))
        if not 0<displacement<=12:displacement=None  # Electric displacement 0 means N/A.
    codes=list(dict.fromkeys(trim(v,80) for v in (row.get('engine_codes') or []) if v))[:20]
    kba=list(dict.fromkeys(trim(v,60) for v in (row.get('kba_numbers') or []) if v))[:20]
    data={'brand':brand,'model':model,'modification':modification,'year_from':start,'year_to':end,
        'displacement_l':displacement,'fuel_type':trim(row.get('fuel_type'),50) or None,
        'power_kw':row.get('power_kw'),'power_ps':row.get('power_ps'),
        'body':trim(row.get('body'),180) or None,'drive_type':row.get('drive_type') or None,
        'engine_codes':codes,'kba_numbers':kba}
    if data['drive_type'] not in (None,'FWD','RWD','AWD','4WD'):
        data['drive_type']=None
    for key in ('power_kw','power_ps'):
        if data[key] is not None:data[key]=int(data[key])
    identity={**data,'displacement_l':str(displacement) if displacement is not None else None}
    key=json.dumps(identity,sort_keys=True,ensure_ascii=False,separators=(',',':'))
    data['id']=hashlib.sha256(key.encode('utf-8')).hexdigest()
    return data

def analyze_payload(raw,filename):
    sha=hashlib.sha256(raw).hexdigest()
    by_id={}
    for item in parse_upload(raw,filename):
        row=validated(item);by_id[row['id']]=row
        if len(by_id)>MAX_ROWS:raise HTTPException(413,'Максимум 40 000 модифікацій')
    if not by_id:raise HTTPException(422,'Не знайдено модифікацій автомобілів')
    return sha, list(by_id.values())

def apply_payload(db,raw,filename,account_id,dry_run=True):
    sha,rows=analyze_payload(raw,filename)
    for r in rows:
        r['id']=hashlib.sha256((account_id+':'+r['id']).encode('utf-8')).hexdigest()
        r['account_id']=account_id
    ids=[r['id'] for r in rows]
    existing=set()
    # One batched query per 1000 keys, avoiding PostgreSQL parameter count limits.
    for n in range(0,len(ids),1000):
        existing.update(db.scalars(select(VehicleDirectoryVariant.id).where(VehicleDirectoryVariant.account_id==account_id,VehicleDirectoryVariant.id.in_(ids[n:n+1000]))))
    fresh=[r for r in rows if r['id'] not in existing]
    result={'sha256':sha,'file':filename[:200],'source_rows':len(rows),'existing':len(rows)-len(fresh),
            'new':len(fresh),'dry_run':dry_run,'no_donor_changes':True}
    if dry_run:return result
    # Serialize importers in a global transaction and re-check after lock.
    db.execute(text('SELECT pg_advisory_xact_lock(6751982026)'))
    already=db.get(VehicleDirectoryImport,(sha,account_id))
    if already:
        return {**result,'new':0,'existing':len(rows),'already_imported':True}
    inserted=0
    for n in range(0,len(rows),400):
        payload=[dict(r,source_sha=sha) for r in rows[n:n+400]]
        stmt=pg_insert(VehicleDirectoryVariant).values(payload).on_conflict_do_nothing(index_elements=['id'])
        inserted+=db.execute(stmt).rowcount
    db.add(VehicleDirectoryImport(account_id=account_id,source_sha=sha,filename=filename[:200],record_count=len(rows),
                                  inserted_count=inserted,imported_at=datetime.now(timezone.utc)))
    db.commit()
    return {**result,'new':inserted,'existing':len(rows)-inserted,'dry_run':False}
