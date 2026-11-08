"""Generated regression shape using public type labels; no private article database.

Aggregate sizes supplied by owner:113 types,736 articles,175 suppliers,
459 articles with OEM,465 with photo metadata,434 type/supplier pairs.
All article numbers, OEM numbers, attributes and supplier names below are synthetic.
"""
import json
from pathlib import Path


def fixture(padded=False):
    root=Path(__file__).resolve().parents[2]
    taxonomy=json.loads((root/'warehouse/docs/unified-catalogue/review/volvo-107555-taxonomy-draft.json').read_text('utf-8'))
    ids=list(map(int,taxonomy))
    pairs=[(ids[i%113], i%175+1) for i in range(434)]
    assert len(set(pairs))==434
    categories={pid:dict(product_id=pid,original=[{'id':pid,'description':taxonomy[str(pid)]['original']}],articles=[]) for pid in ids}
    articles={}
    for i in range(736):
        pid,sid=pairs[i%434]
        number=f'SYNTHETIC-{i:05d}'
        key=f'{sid}:{number}'
        articles[key]=dict(supplier_id=sid,article_number=number,car_id=107555,
            article=[{'supplierId':sid,'DataSupplierArticleNumber':number,'NormalizedDescription':'Synthetic article only'}],
            supplier=[{'id':sid,'description':f'Synthetic supplier {sid}'}],
            oem=[{'manufacturerId':120,'OENbr':f'SYN-OEM-{i}'}] if i<459 else [],
            images=[{'PictureName':f'SYN-{i}.JPG'}] if i<465 else [],
            attributes=[{'description':'Synthetic attribute','value':'fixture'}],crosses=[],image_status='metadata_only')
        if padded:articles[key]['synthetic_padding']='generated fixture only '*200
        categories[pid]['articles'].append(key)
    return dict(schema='carpot.volvo.v1',manufacturer_id=120,car_id=107555,model_id=13084,
        modification={'id':107555,'modelid':13084,'description':'T6 AWD'},model={'id':13084},
        details={'passanger_car_pds':[dict(passangercarid=107555,productid=pid,supplierid=sid,nodeid=i) for i,(pid,sid) in enumerate(pairs)]},
        categories=list(categories.values()),articles=articles,collection_complete=True,coverage='partial',
        observed_at='2026-11-08T12:00:00+00:00',image_status='metadata_only')
