"""Verify the supplied outer ZIP and extract only to a fresh system temporary folder.

MANIFEST.json contract: {"files": {"relative/path": "sha256"}} or a list of
{"path": "relative/path", "sha256": "..."}. Documents are data, never executed.
"""
import argparse,hashlib,json,re,stat,tempfile,zipfile
from pathlib import Path,PurePosixPath


def verify(archive):
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist()
        if len(infos)>1000 or sum(i.file_size for i in infos)>512*1024*1024:raise ValueError('Archive exceeds inspection limits')
        names=set()
        for i in infos:
            path=PurePosixPath(i.filename)
            if '\\' in i.filename or ':' in i.filename or path.is_absolute() or '..' in path.parts or stat.S_ISLNK(i.external_attr>>16):raise ValueError('Unsafe archive path')
            if i.filename in names:raise ValueError('Duplicate archive path')
            names.add(i.filename)
        manifests=[i.filename for i in infos if PurePosixPath(i.filename).name=='MANIFEST.json']
        if len(manifests)!=1:raise ValueError('Exactly one MANIFEST.json required')
        if z.getinfo(manifests[0]).file_size>1024*1024:raise ValueError('Manifest too large')
        manifest=json.loads(z.read(manifests[0]));entries=manifest['files'];prefix=str(PurePosixPath(manifests[0]).parent)
        if isinstance(entries,list):
            if len({r['path'] for r in entries})!=len(entries):raise ValueError('Duplicate manifest path')
            entries={r['path']:r['sha256'] for r in entries}
        if not isinstance(entries,dict) or not entries:raise ValueError('Unsupported/empty manifest')
        checked={}
        for name,expected in entries.items():
            if not isinstance(expected,str) or not re.fullmatch('[a-fA-F0-9]{64}',expected):raise ValueError('Invalid expected checksum')
            actual=name if name in names else str(PurePosixPath(prefix)/name)
            if actual not in names or actual==manifests[0]:raise ValueError('Manifest member missing')
            h=hashlib.sha256()
            with z.open(actual) as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            if h.hexdigest()!=expected.lower():raise ValueError('Checksum mismatch: '+name)
            checked[actual]=h.hexdigest()
        # Unlisted members must not enter the extracted evidence directory.
        extras={i.filename for i in infos if not i.is_dir()}-set(checked)-{manifests[0]}
        if extras:raise ValueError('Unlisted archive members')
        folder=Path(tempfile.mkdtemp(prefix='carpot-catalogue-inputs-'))
        for name in [manifests[0],*checked]:
            target=folder.joinpath(*PurePosixPath(name).parts);target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(name) as source,target.open('xb') as dest:
                for block in iter(lambda:source.read(1024*1024),b''):dest.write(block)
        return dict(directory=str(folder),verified=checked)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('archive',type=Path)
    print(json.dumps(verify(parser.parse_args().archive),ensure_ascii=False,indent=2))
