"""Stage 12: conservative VIN-to-Catalogue selection for any manufacturer.

Catalogue directory records are *candidates*, never proof of VIN fitment. A
selected record is re-read by its immutable source IDs and pinned snapshot
before it is allowed into a donor's plan. All lookups are free read-only calls.
"""
import re
import unicodedata
from fastapi import HTTPException

from app.services import unified_catalogue as catalogue

_ROMAN = frozenset(("i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x"))
_HEX_SHA = re.compile(r"^[a-f0-9]{64}$")


def normalized(value):
    return "".join(c for c in unicodedata.normalize("NFKC", str(value or "")).casefold() if c.isalnum())


def same_model(vehicle_model, catalogue_model, generation=""):
    """No fuzzy/substring match: allow only an explicit roman generation suffix."""
    a, b = normalized(vehicle_model), normalized(catalogue_model)
    if not a or not b:
        return False
    if a == b or (generation and normalized(str(vehicle_model) + " " + str(generation)) == b):
        return True
    suffix = b[len(a):] if b.startswith(a) else ""
    return suffix in _ROMAN if suffix else False


def valid_candidate(item):
    if not isinstance(item, dict):
        return False
    for field in ("source_modification_id", "model_id", "manufacturer_id"):
        if type(item.get(field)) is not int or item[field] <= 0:
            return False
    if not isinstance(item.get("snapshot_sha"), str) or not _HEX_SHA.fullmatch(item["snapshot_sha"]):
        return False
    if not all(isinstance(item.get(field), str) and item[field].strip() for field in ("manufacturer", "model")):
        return False
    if not isinstance(item.get("modification"), dict):
        return False
    return True


def candidate_public(item, model_hint):
    return dict(
        source_modification_id=item["source_modification_id"],
        model_id=item["model_id"],
        manufacturer_id=item["manufacturer_id"],
        source_snapshot_sha=item["snapshot_sha"],
        manufacturer=item["manufacturer"],
        model=item["model"],
        generation=item.get("generation") or "",
        modification=str(item["modification"].get("description") or "Модифікація без назви")[:350],
        type_count=item.get("type_count", 0),
        coverage=item.get("coverage", "unknown"),
        model_matches=bool(model_hint and same_model(model_hint, item["model"], item.get("generation") or "")),
        vin_fitment_verified=False,
    )


def search_candidates(adapter, *, manufacturer, model="", after=0, limit=40, max_pages=6):
    """Bounded paginated search; preserve upstream cursor and never claim exhaustiveness.

    maker_key is a provider-side *hint*. Every returned manufacturer is checked
    locally; older Catalogue services can ignore the filter safely.
    """
    make = normalized(manufacturer)
    if len(make) < 2:
        raise HTTPException(422, "Уточніть марку автомобіля")
    cursor = after
    found = []
    seen = set()
    scanned = 0
    next_after = None
    for _ in range(max_pages):
        try:
            page = adapter.directory(after=cursor, maker_key=make)
        except catalogue.CatalogueUnavailable:
            raise HTTPException(503, "Каталог модифікацій тимчасово недоступний") from None
        if not isinstance(page, dict) or not isinstance(page.get("items"), list):
            raise HTTPException(503, "Некоректна відповідь каталогу модифікацій")
        for item in page["items"]:
            if not valid_candidate(item) or normalized(item["manufacturer"]) != make:
                continue
            sid = item["source_modification_id"]
            if sid in seen:
                continue
            seen.add(sid)
            found.append(candidate_public(item, model))
            if len(found) >= limit:
                break
        scanned += len(page["items"])
        next_after = page.get("next_after")
        if next_after is not None and (type(next_after) is not int or next_after <= cursor):
            raise HTTPException(503, "Некоректна пагінація каталогу")
        if next_after is None or len(found) >= limit:
            break
        cursor = next_after
    found.sort(key=lambda v:(not v["model_matches"], normalized(v["model"]), normalized(v["modification"]), v["source_modification_id"]))
    return dict(items=found, next_after=next_after, search_complete=next_after is None,
                scanned=scanned, source="carpot.catalogue.v1", vin_fitment_verified=False)


def validate_selection(adapter, *, selection, manufacturer, model, generation="", year=None):
    """Read-only revalidation; returns the source record and immutable plan.

    No article/OEM reference alone proves exact fitment. Reject all identity
    mismatches rather than silently correcting the user-confirmed VIN fields.
    """
    try:
        entries = adapter.directory(car_id=selection.source_modification_id)["items"]
        entry = next((r for r in entries
                      if valid_candidate(r) and r["source_modification_id"] == selection.source_modification_id), None)
        plan = adapter.plan(selection.source_modification_id, global_source=True)
    except (catalogue.CatalogueUnavailable, KeyError, ValueError, TypeError):
        raise HTTPException(503, "Не вдалося перевірити обрану модифікацію") from None
    if not entry:
        raise HTTPException(409, "Модифікацію не знайдено у підтвердженому каталозі")
    expected = (selection.source_modification_id, selection.model_id,
                selection.manufacturer_id, selection.source_snapshot_sha)
    observed = (entry["source_modification_id"], entry["model_id"],
                entry["manufacturer_id"], entry["snapshot_sha"])
    payload = plan.get("payload", {})
    actual = (payload.get("car_id"), payload.get("model_id"),
              payload.get("manufacturer_id"), payload.get("source_snapshot_sha"))
    if observed != expected or actual != expected or not payload.get("categories"):
        raise HTTPException(409, "Каталожні ID або версія модифікації змінилися")
    if normalized(manufacturer) != normalized(entry["manufacturer"]):
        raise HTTPException(409, "Марка автомобіля не збігається з каталогом")
    if not same_model(model, entry["model"], generation):
        raise HTTPException(409, "Модель автомобіля не збігається з обраною модифікацією")
    start, end = entry.get("year_from"), entry.get("year_to")
    if year is not None and (type(start) is int and year < start or type(end) is int and year > end):
        raise HTTPException(409, "Рік автомобіля поза підтвердженим діапазоном модифікації")
    return entry, plan
