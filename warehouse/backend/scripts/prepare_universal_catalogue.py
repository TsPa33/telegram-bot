"""Offline PRD/review preparation. Never opens a database or calls translation APIs."""
import argparse,csv,io,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.universal_catalogue import prepare
from app.services.catalogue_format import digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True,type=Path);p.add_argument('--reviews',type=Path);p.add_argument('--known-types',type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--batch-dir',type=Path,help='Write sequential 500-row preview requests outside the repository; no HTTP calls')
    a=p.parse_args()
    repository=Path(__file__).resolve().parents[3]
    if a.output.resolve().is_relative_to(repository) or (a.batch_dir and a.batch_dir.resolve().is_relative_to(repository)):p.error('Raw review evidence must be written outside the Git repository')
    if a.batch_dir and a.batch_dir.exists() and any(a.batch_dir.iterdir()):p.error('Use a new empty batch directory')
    text=a.input.read_text(encoding='utf-8-sig')
    if a.input.suffix.lower()=='.csv':
        dialect=csv.Sniffer().sniff(text[:8192],delimiters=',;\t')
        rows=list(csv.DictReader(io.StringIO(text),dialect=dialect))
        for row in rows:
            if not str(row.get('id','')).isdigit():p.error('CSV requires explicit numeric PRD id column')
            row['id']=int(row['id'])
    else:rows=json.loads(text)
    reviews=json.loads(a.reviews.read_text(encoding='utf-8-sig')) if a.reviews else []
    known=json.loads(a.known_types.read_text(encoding='utf-8-sig')) if a.known_types else None
    result=prepare(rows,reviews,known)
    if a.output.exists():p.error('Refusing to overwrite an existing report; use a new output path')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    if a.batch_dir:
        a.batch_dir.mkdir(parents=True,exist_ok=True)
        for offset in range(0,len(rows),500):
            chunk=rows[offset:offset+500];ids={r['id'] for r in chunk}
            request=dict(rows=chunk,reviews=[r for r in reviews if r['source_id'] in ids],input_sha=digest(chunk))
            with (a.batch_dir/f'preview-{offset//500+1:05d}.json').open('x',encoding='utf-8') as f:json.dump(request,f,ensure_ascii=False,indent=2)
    print(json.dumps(result['counts'],ensure_ascii=False))
if __name__=='__main__':main()
