"""Offline, lossless Aleto CSV -> Import v2 ZIP. Never opens a Warehouse DB."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import zipfile
from app.services.aleto_import import CATEGORY_ALIASES, DICTIONARY, money
from app.services.catalogue_format import MAX_EXPANDED, MAX_ROWS, ImportRow, parse_upload

FIELDS = ['schema_version','source','source_article','manufacturer','model','generation','year_from','year_to',
          'category','subcategory','part_name','oem','condition','side','position','price_uah','price_usd',
          'source_url','observed_at','source_record']
RAW_REQUIRED = {'article','model','category','subcategory','title','url','checked_at'}
KNOWN_MODELS = {'Volvo XC40':('Volvo','XC40'),'Volvo XC60':('Volvo','XC60'),'Volvo XC90':('Volvo','XC90')}


def read_csv(path):
    raw=Path(path).read_bytes()
    if len(raw)>MAX_EXPANDED:raise ValueError('Input CSV exceeds 64 MiB')
    csv.field_size_limit(4096)
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''),strict=True)
    fields=reader.fieldnames or []
    if not fields or any(not name or len(name)>128 for name in fields) or len(set(fields))!=len(fields) or len(fields)>128:raise ValueError('Missing/duplicate/excessive CSV headers')
    rows=[]
    for index,row in enumerate(reader,2):
        if index>MAX_ROWS+1:raise ValueError('Input exceeds 50000 rows')
        if None in row or any(v is None for v in row.values()):raise ValueError(f'Wrong CSV field count at row {index}')
        rows.append(row)
    if not rows:raise ValueError('Input CSV is empty')
    return fields,rows,hashlib.sha256(raw).hexdigest()


def split_model(value,manufacturer=None):
    label=value.strip()
    if manufacturer:
        manufacturer=manufacturer.strip()
        prefix=manufacturer+' '
        if not manufacturer or not label.casefold().startswith(prefix.casefold()):
            raise ValueError('Raw model must begin with the explicitly selected manufacturer and a space')
        model=label[len(prefix):].strip()
        if not model:raise ValueError('Missing model')
        return manufacturer,model
    if label not in KNOWN_MODELS:
        raise ValueError('Unknown raw model: supply --manufacturer explicitly; no brand/year inference is performed')
    return KNOWN_MODELS[label]


def converted(record,manufacturer=None,prepared=False):
    brand,model=split_model(record['model'],manufacturer)
    raw_category=record['category_source'] if prepared else record['category']
    raw_subcategory=record['subcategory_raw'] if prepared else record['subcategory']
    category=record['category_uk'] if prepared else CATEGORY_ALIASES.get(raw_category,raw_category)
    subcategory=DICTIONARY.get(raw_subcategory) or raw_subcategory
    if 'source' in record and record['source']!='aleto':raise ValueError('This profile accepts only Aleto source records')
    if record.get('price_status') and record['price_status']!=('missing' if money(record.get('price_uah')) is None else 'observed'):
        raise ValueError('price_status contradicts price_uah')
    values=dict(schema_version='2',source='aleto',source_article=record['article'],manufacturer=brand,model=model,
        category=category,subcategory=subcategory,part_name=record['title'],source_url=record['url'],observed_at=record['checked_at'])
    for key in ('generation','year_from','year_to','oem','condition','side','position','price_uah','price_usd'):
        if key in record:values[key]=record[key]
    # Every original field is retained verbatim in the immutable job payload.
    values['source_record']=dict(record)
    parsed=ImportRow.model_validate(values).model_dump()
    parsed['source_record']=json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return {name:parsed.get(name) for name in FIELDS}


def merge_records(*records):
    combined={}
    for record in records:
        for key,value in record.items():
            if key in combined and combined[key]!=value:raise ValueError('Prepared CSV join has conflicting shared fields')
            combined[key]=value
    return combined


def convert(input_path,manufacturer=None):
    path=Path(input_path)
    rows=[];inputs={}
    if path.is_dir():
        of,offers,inputs['offers.csv']=read_csv(path/'offers.csv')
        af,applications,inputs['applications.csv']=read_csv(path/'applications.csv')
        tf,paths,inputs['taxonomy_paths.csv']=read_csv(path/'taxonomy_paths.csv')
        if not {'article','title','url','checked_at'}<=set(of) or not {'model','article'}<=set(af) or not {'model','article','category_uk','category_source','subcategory_raw'}<=set(tf):
            raise ValueError('Unsupported prepared CSV schema')
        by_article={r['article']:r for r in offers}
        if len(by_article)!=len(offers):raise ValueError('Prepared offers must contain one row per article; use raw profile for multiple observations')
        apps={(r['model'],r['article']):r for r in applications}
        if len(apps)!=len(applications):raise ValueError('Duplicate application')
        seen=set();covered=set()
        for record in paths:
            pair=(record['model'],record['article'])
            if pair not in apps or record['article'] not in by_article:raise ValueError('Prepared taxonomy has an orphan relationship')
            seen.add(pair);covered.add(record['article'])
            rows.append(converted(merge_records(by_article[record['article']],apps[pair],record),manufacturer,True))
        if seen!=set(apps) or covered!=set(by_article):raise ValueError('Prepared inputs have missing taxonomy or offers')
        profile='aleto-prepared-csv'
    else:
        fields,records,checksum=read_csv(path);inputs[path.name]=checksum
        if not RAW_REQUIRED<=set(fields):raise ValueError('Raw Aleto CSV lacks article/model/category/subcategory/title/url/checked_at; do not guess column mappings')
        rows=[converted(r,manufacturer) for r in records]
        profile='aleto-parser-csv'
    output=io.StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=FIELDS,lineterminator='\n');writer.writeheader();writer.writerows(rows)
    raw=output.getvalue().encode('utf-8-sig')
    manifest={'schema_version':2,'file':'catalogue.csv','sha256':hashlib.sha256(raw).hexdigest()}
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,content in [('manifest.json',json.dumps(manifest).encode()),('catalogue.csv',raw)]:
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,content)
    result=buffer.getvalue()
    verified,fmt=parse_upload(result,'catalogue.zip')
    if len(verified)!=len(rows):raise ValueError('Conversion row count mismatch')
    report={'profile':profile,'input_sha256':inputs,'rows':len(rows),'offers':len({(r['source'],r['source_article']) for r in verified}),
            'applications':len({(r['manufacturer'],r['model'],r['source_article']) for r in verified}),
            'paths':len({(r['manufacturer'],r['model'],r['source_article'],r.get('_raw_category',r['category']),r.get('_raw_subcategory',r['subcategory'])) for r in verified}),
            'csv_sha256':manifest['sha256'],'zip_sha256':hashlib.sha256(result).hexdigest(),
            'source_record_preserved':True,'staging_operations':False}
    return result,report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path,help='Raw parser CSV or directory with prepared offers/applications/taxonomy CSVs')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--manufacturer',help='Explicit manufacturer for raw full model labels outside the three known Volvo names')
    args=parser.parse_args()
    if args.output.exists() or args.report.exists():parser.error('Output/report already exists; choose new paths to preserve previous files')
    try:
        raw,report=convert(args.input,args.manufacturer)
        args.output.write_bytes(raw);args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    except (ValueError,csv.Error,OSError) as exc:parser.exit(1,f'Conversion rejected: {exc}\n')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
