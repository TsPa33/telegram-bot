"""Authenticated, read-only Oracle vehicle identity browser.

The Oracle directory is NOT a pinned parts graph: discovering a modification
does not establish VIN fitment, OEM applicability, or a source dismantling plan.
"""
import re
import unicodedata
from fastapi import HTTPException
from app.services.unified_catalogue import CatalogueAdapter, CatalogueUnavailable


def norm(value):
    return "".join(c for c in unicodedata.normalize("NFKD",str(value or "")).casefold() if c.isalnum())


# Regional rows are alternate identities. Their IDs and namespaces remain separate.
_MAKE_ALIASES = {
    "volkswagen": ("Volkswagen", "VW"),
    "mercedesbenz": ("Mercedes-Benz", "Mercedes Benz"),
}
_REGION = re.compile(r"\s*\((?:usa|us|nordamerika|north america|europa|europe|japan|china|south africa|brazil|brasil|faw|svw|shanghai)\)$", re.I)


def maker_key(name):
    normalized = norm(_REGION.sub("", name).strip())
    return next((key for key, aliases in _MAKE_ALIASES.items()
                 if normalized in {norm(alias) for alias in aliases}), normalized)


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


def manufacturer_choices(name, adapter=None, *, kinds=("passenger", "commercial")):
    """Return exact make matches in both passenger and commercial namespaces."""
    name=name.strip()
    query = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    prefix = re.match(r"[A-Za-z0-9 .-]+", query)
    prefix = prefix[0].strip() if prefix else ""
    if len(name) > 100 or not 2 <= len(prefix) <= 40:
        raise HTTPException(422, "Уточніть назву виробника з довідника")
    adapter=adapter or CatalogueAdapter()
    values = {}
    unavailable = []
    identity = maker_key(name)
    prefixes = tuple(dict.fromkeys((prefix, *_MAKE_ALIASES.get(identity, ()))))
    for kind in kinds:
        for term in prefixes:
            try:
                response = fetch(adapter, "manufacturers", {"name": term, "kind": kind, "limit": 50}, kind)
            except HTTPException as error:
                if error.status_code != 503:
                    raise
                unavailable.append(kind)
                continue
            if response.get("truncated") is True:
                unavailable.append(kind)
            for item in response["items"]:
                if (isinstance(item, dict) and type(item.get("id")) is int and item["id"] > 0
                        and isinstance(item.get("name"), str) and maker_key(item["name"]) == identity):
                    values[(kind, item["id"])] = dict(
                        manufacturer_id=item["id"], manufacturer=item["name"], kind=kind)
    if not values and unavailable:
        raise HTTPException(503,"Не вдалося завантажити виробника з каталогу")
    return dict(items=list(values.values()), partial=bool(unavailable), source="oracle",
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
            not isinstance(item, dict) or type(item.get("id")) is not int or item["id"]<=after
            or not isinstance(item.get("name"),str)
            or (endpoint=="modifications" and item.get("model_id")!=source_id)
            for item in items):
        raise HTTPException(503,"Некоректні дані модифікацій")
    if any(a["id"] >= b["id"] for a, b in zip(items, items[1:])):
        raise HTTPException(503,"Некоректний порядок модифікацій")
    next_after=data.get("next_after")
    if next_after is not None and (type(next_after) is not int or next_after<=after
                                   or not items or next_after!=items[-1]["id"]):
        raise HTTPException(503,"Некоректний курсор каталогу")
    return dict(items=[dict(id=item["id"],name=item["name"],
                            construction_interval=item.get("construction_interval"))
                       for item in items],
                next_after=next_after, identity_only=True, vin_fitment_verified=False)


def confirm_identity(selection, *, manufacturer, model, adapter=None, maker_checked=False):
    """O(1) indexed re-read of the chosen model and modification in its maker.

    The client supplies numeric identifiers, never trusted names. Check each
    containment edge through the authenticated Oracle catalogue.
    """
    adapter=adapter or CatalogueAdapter()
    if not maker_checked:
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




def manufacturer_page(adapter, *, kind, name="", after=0, limit=50):
    result = fetch(adapter, "manufacturer-directory", dict(kind=kind, name=name, after=after, limit=limit), kind)
    items = result["items"]
    ids = [item.get("id") for item in items if isinstance(item, dict)]
    cursor = result.get("next_after")
    if (len(ids) != len(items) or len(items) > limit
            or any(type(i) is not int or i <= after for i in ids)
            or ids != sorted(set(ids))
            or any(not isinstance(item.get("name"), str) or not item["name"] for item in items)
            or (cursor is not None and (len(ids) != limit or cursor != ids[-1]))):
        raise HTTPException(503, "Некоректна відповідь довідника виробників")
    return dict(items=items, next_after=cursor)


def catalogue_identity(adapter, selection, *, manufacturer, model, year=None):
    from app.services.vin_resolution_policy import interval, source_specs

    makers = manufacturer_page(adapter, kind=selection.kind, after=selection.manufacturer_id - 1, limit=1)
    maker = next((row for row in makers["items"] if row["id"] == selection.manufacturer_id), None)
    if not maker or norm(maker["name"]) != norm(manufacturer):
        raise HTTPException(409, "Виробник змінився. Повторіть вибір із каталогу")
    identity = confirm_identity(selection, manufacturer=manufacturer, model=model, adapter=adapter, maker_checked=True)
    start, end = interval(identity["construction_interval"])
    if year and ((start and year < start) or (end and year > end)):
        raise HTTPException(422, "Рік автомобіля поза періодом виробництва обраної модифікації")
    try:
        attributes = fetch(adapter, "attributes",
                           dict(kind=identity["kind"], car_id=identity["source_modification_id"], limit=50),
                           identity["kind"])
    except HTTPException as error:
        if error.status_code != 503:
            raise
        return identity, [], {}
    if attributes.get("source_modification_id") != identity["source_modification_id"]:
        raise HTTPException(503, "Некоректні характеристики модифікації")
    fields = {field: next(iter(values.items())) for field, values in source_specs(attributes["items"]).items()}
    return identity, attributes["items"], fields
