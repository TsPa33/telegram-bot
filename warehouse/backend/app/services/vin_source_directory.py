"""Authenticated, read-only Oracle vehicle identity browser.

The Oracle directory is NOT a pinned parts graph: discovering a modification
does not establish VIN fitment, OEM applicability, or a source dismantling plan.
"""
import re
import unicodedata
from fastapi import HTTPException
from app.services.unified_catalogue import CatalogueAdapter, CatalogueUnavailable


def norm(value):
    return "".join(c for c in unicodedata.normalize("NFKC",str(value or "")).casefold() if c.isalnum())


def fetch(adapter, endpoint, args, expected_kind=None):
    try:
        result=adapter.get("global:oracle/vehicles/"+endpoint,args)
    except CatalogueUnavailable:
        raise HTTPException(503,"Довідник модифікацій тимчасово недоступний") from None
    if (not isinstance(result,dict) or result.get("source")!="oracle"
            or result.get("vehicle_identity_only") is not True
            or result.get("fitment_verified") is not False
            or not isinstance(result.get("items"),list)
            or (expected_kind and result.get("kind")!=expected_kind)):
        raise HTTPException(503,"Некоректна відповідь довідника автомобілів")
    return result


def manufacturer_choices(name, adapter=None):
    """Return exact make matches in both passenger and commercial namespaces."""
    name=name.strip()
    if len(name)<2 or len(name)>40 or not re.fullmatch(r"[A-Za-z0-9 .-]+",name):
        raise HTTPException(422,"Уточніть марку латинськими літерами")
    adapter=adapter or CatalogueAdapter()
    values=[]
    unavailable=[]
    for kind in ("passenger","commercial"):
        try:
            response=fetch(adapter,"manufacturers",{"name":name,"kind":kind,"limit":50},kind)
        except HTTPException as e:
            if e.status_code==503:
                unavailable.append(kind)
                continue
            raise
        for item in response["items"]:
            if (type(item.get("id")) is int and item["id"]>0
                    and isinstance(item.get("name"),str)
                    and norm(item["name"])==norm(name)):
                values.append(dict(manufacturer_id=item["id"],manufacturer=item["name"],kind=kind))
    if not values and unavailable:
        raise HTTPException(503,"Не вдалося завантажити виробника з каталогу")
    return dict(items=values, partial=bool(unavailable), source="oracle",
                identity_only=True, vin_fitment_verified=False)


def source_page(endpoint, *, source_id, kind, after=0, adapter=None):
    if kind not in ("passenger","commercial"):
        raise HTTPException(422,"Некоректний тип транспортного засобу")
    if type(source_id) is not int or source_id<=0 or type(after) is not int or after<0:
        raise HTTPException(422,"Некоректний каталожний ID")
    adapter=adapter or CatalogueAdapter()
    key="manufacturer_id" if endpoint=="models" else "model_id"
    data=fetch(adapter,endpoint,{key:source_id,"kind":kind,"after":after,"limit":50},kind)
    items=data["items"]
    if len(items)>50 or any(
            type(item.get("id")) is not int or item["id"]<=after
            or not isinstance(item.get("name"),str)
            or (endpoint=="modifications" and item.get("model_id")!=source_id)
            for item in items):
        raise HTTPException(503,"Некоректні дані модифікацій")
    next_after=data.get("next_after")
    if next_after is not None and (type(next_after) is not int or next_after<=after
                                   or not items or next_after!=items[-1]["id"]):
        raise HTTPException(503,"Некоректний курсор каталогу")
    return dict(items=[dict(id=item["id"],name=item["name"],
                            construction_interval=item.get("construction_interval"))
                       for item in items],
                next_after=next_after, identity_only=True, vin_fitment_verified=False)


def confirm_identity(selection, *, manufacturer, model, adapter=None):
    """O(1) indexed re-read of the chosen model and modification in its maker.

    The client supplies numeric identifiers, never trusted names. Check each
    containment edge through the authenticated Oracle catalogue.
    """
    adapter=adapter or CatalogueAdapter()
    makers=manufacturer_choices(manufacturer,adapter)
    if not any(item["manufacturer_id"]==selection.manufacturer_id
               and item["kind"]==selection.kind for item in makers["items"]):
        raise HTTPException(409,"Виробник модифікації не збігається з VIN")
    model_page=source_page("models",source_id=selection.manufacturer_id,
                           kind=selection.kind,after=selection.model_id-1,adapter=adapter)
    model_row=next((r for r in model_page["items"] if r["id"]==selection.model_id),None)
    if not model_row or norm(model)!=norm(model_row["name"]):
        raise HTTPException(409,"Модель не відповідає довіднику. Повторіть вибір")
    variant_page=source_page("modifications",source_id=selection.model_id,
                             kind=selection.kind,after=selection.source_modification_id-1,adapter=adapter)
    variant=next((r for r in variant_page["items"] if r["id"]==selection.source_modification_id),None)
    if not variant:
        raise HTTPException(409,"Модифікацію не знайдено у моделі")
    return dict(source="oracle",manufacturer_id=selection.manufacturer_id,
                model_id=selection.model_id,source_modification_id=selection.source_modification_id,
                kind=selection.kind,model=model_row["name"],
                modification=variant["name"],
                construction_interval=variant.get("construction_interval"),
                confirmation="user_selected_identity_only",
                vin_fitment_verified=False, parts_graph_verified=False)


