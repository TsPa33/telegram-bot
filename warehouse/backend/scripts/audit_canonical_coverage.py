"""Read-only offline term audit of a Catalogue v2 package (no database/network)."""
import argparse,json,sys
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.catalogue_format import parse_upload
from app.services.aleto_import import BUNDLED_PACKAGE
from app.services.canonical_rules import classify,RULES,RULE_FINGERPRINT

def audit(package):
    rows,_=parse_upload(package.read_bytes(),package.name)
    groups=defaultdict(lambda:{'paths':0,'offers':set(),'examples':[]})
    quality=Counter();mapped=set();types=set();offers=set()
    for i,row in enumerate(rows):
        source=dict(key='offline:'+str(i),sha='',title=row['part_name'],category=row['category'],subcategory=row['subcategory'],manufacturer=row['manufacturer'],model=row['model'],oem=row['oem'],article=row['source_article'],side=row['side'],position=row['position'])
        result=classify(source);quality[result['quality']]+=1;offers.add(row['source_article'])
        if result['quality'].startswith('verified'):
            mapped.add(row['source_article']);types.add(result['type_id']);continue
        phrase=result['evidence']['normalization']['phrase'];key=(source['category'],source['subcategory'],phrase,result.get('reason'))
        group=groups[key];group['paths']+=1;group['offers'].add(row['source_article'])
        if len(group['examples'])<3 and source['title'] not in group['examples']:group['examples'].append(source['title'])
    return dict(scope='offline package paths only; full v2 publication measured separately',rule_version=RULES['version'],rules_sha=RULE_FINGERPRINT,source_offers=len(offers),mapped_offers=len(mapped),coverage_percent=100*len(mapped)/len(offers),market_type_count=len(types),quality=dict(quality),unresolved_groups=[dict(category=k[0],subcategory=k[1],phrase=k[2],reason=k[3],paths=g['paths'],offers=len(g['offers']),examples=g['examples']) for k,g in sorted(groups.items(),key=lambda x:(-x[1]['paths'],x[0]))])
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package',type=Path,default=BUNDLED_PACKAGE);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.write_text(json.dumps(audit(args.package),ensure_ascii=False,indent=2)+'\n')
