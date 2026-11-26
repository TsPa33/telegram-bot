"""Validate and import a complete local 12-type body library; no APIs or DB."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

KINDS = ('sedan','hatchback','wagon','suv','coupe','convertible','minivan','pickup','van','tractor','truck','bus')
MAX_BYTES=150000

def validate(root):
    meta=json.loads((root/'metadata.json').read_text(encoding='utf-8'))
    if set(meta)!=set(KINDS):
        raise ValueError('Incomplete body library; missing: '+', '.join(sorted(set(KINDS)-set(meta))))
    result=[]
    for kind in KINDS:
        a=meta[kind]
        name='body-'+kind+'.webp'
        if a.get('file')!=name: raise ValueError('Unexpected file '+kind)
        raw=(root/name).read_bytes()
        if len(raw)>MAX_BYTES or len(raw)<30 or raw[:4]!=b'RIFF' or raw[8:16]!=b'WEBPVP8X' or not raw[20]&16:
            raise ValueError('Transparent WebP required: '+kind)
        if struct.unpack_from('<I',raw,4)[0]+8!=len(raw):
            raise ValueError('Truncated WebP '+kind)
        width=int.from_bytes(raw[24:27],'little')+1
        height=int.from_bytes(raw[27:30],'little')+1
        if (width,height)!=(960,640) or (a.get('width'),a.get('height'))!=(width,height):
            raise ValueError('Unexpected canvas '+kind)
        if hashlib.sha256(raw).hexdigest()!=a.get('sha256') or len(raw)!=a.get('bytes'):
            raise ValueError('Hash/length mismatch '+kind)
        if 'OpenAI generated generic body illustration' not in a.get('source',''):
            raise ValueError('Missing provenance '+kind)
        result.append((kind,raw,a))
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    p.add_argument('--apply',action='store_true',help='Write local source assets only after all twelve validate')
    args=p.parse_args()
    rows=validate(args.directory)
    print('PASS',len(rows),'body images',sum(len(b) for _,b,_ in rows),'bytes')
    if not args.apply:return
    frontend=Path(__file__).resolve().parents[1]
    target=frontend/'src/assets/vehicles'
    registry=[]
    for kind,raw,a in rows:
        (target/a['file']).write_bytes(raw)
        registry.append(dict(id='body-'+kind+'-v2',kind='body',bodyType=kind,file=a['file'],width=a['width'],height=a['height'],verified=True,transparentCutout=True,priority=10,
            source=dict(type='generated',description='Generic body illustration; not a donor or exact model photograph.',reference='src/assets/vehicles/body-library-provenance.json'),
            usage=dict(status='approved',license='OpenAI-generated output; use subject to applicable terms.',commercialUse=True)))
    (target/'body-library-provenance.json').write_text(json.dumps({kind:a for kind,_,a in rows},indent=2)+'\n',encoding='utf-8')
    (frontend/'src/vehicleBodyAssets.ts').write_text("import type {ImageAsset} from './vehicleImageTypes';\nexport const vehicleBodyAssets: readonly ImageAsset[] = "+json.dumps(registry,indent=2)+";\n",encoding='utf-8')
if __name__=='__main__':main()
