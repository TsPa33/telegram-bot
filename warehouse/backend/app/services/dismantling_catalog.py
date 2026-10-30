"""Explicit account-local import. No suppliers, compatibility inference or deletion."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Account, DismantlingCatalogSource as Source, DismantlingCatalogType as Type
from app.services.inventory import record, snapshot

FIELDS=('catalog_key','category_key','category_name','subcategory_key','subcategory_name','name','position','applicability')


def import_catalog(db, account_id, data, dry_run=False):
    # Serialize account imports and existing category imports; no vehicle locks.
    if not dry_run:db.scalar(select(Account).where(Account.id==account_id).with_for_update())
    source=db.scalar(select(Source).where(Source.account_id==account_id,Source.source==data.source))
    existing={r.catalog_key:r for r in db.scalars(select(Type).where(Type.account_id==account_id,Type.source_id==source.id))} if source else {}
    # Existing keys not in the upload remain. Conflicting hierarchy names require
    # a complete consistent rename, not two names for one key within a source.
    combined={key:{k:getattr(row,k) for k in FIELDS} for key,row in existing.items()}
    combined.update({row.catalog_key:row.model_dump() for row in data.types})
    names={}
    for row in combined.values():
        for key,name in [(('cat',row['category_key']),row['category_name']),
                         (('sub',row['category_key'],row['subcategory_key']),row['subcategory_name'])]:
            if key in names and names[key]!=name:raise HTTPException(422,'Суперечливі назви ієрархії для однакового ключа')
            names[key]=name
    created=sum(row.catalog_key not in existing for row in data.types)
    result={'created':created,'updated':len(data.types)-created,'total':len(combined),'dry_run':dry_run}
    if dry_run:return result
    before=snapshot(source) if source else {}
    if source is None:
        source=Source(account_id=account_id,source=data.source,provenance=data.provenance,license_reference=data.license_reference)
        db.add(source);db.flush()
    source.provenance,source.license_reference=data.provenance,data.license_reference
    for item in data.types:
        row=existing.get(item.catalog_key)
        if row is None:
            row=Type(account_id=account_id,source_id=source.id,**item.model_dump());db.add(row)
        else:
            for key,value in item.model_dump().items():setattr(row,key,value)
    record(db,account_id,source,'dismantling_catalog_import',f'Права підтверджено користувачем; нових {created}, оновлено {result["updated"]}; без зміни донорів/складу',before)
    return result


def imported_types(db,account_id):
    for row,source in db.execute(select(Type,Source).join(Source,Type.source_id==Source.id).where(
        Type.account_id==account_id,Source.account_id==account_id)):
        yield {'source':'local.'+source.id,**{key:getattr(row,key) for key in FIELDS}}
