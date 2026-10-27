"""Small independently maintained name suggestions, never a compatibility catalogue."""
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from app.models import Vehicle

NAMES = json.loads((Path(__file__).resolve().parents[1] / "data/vehicle_names.json").read_text())


def local_catalog(db, account_id):
    # No provider fixture, external request, K-Type or inferred production years.
    catalog = {brand: list(models) for brand, models in NAMES.items()}
    from app.models.aleto import AletoModel
    for row in db.scalars(select(AletoModel).where(AletoModel.account_id == account_id)):
        values = catalog.setdefault(row.manufacturer, [])
        if row.model not in values:
            values.append(row.model)
    canonical = {brand.casefold(): brand for brand in catalog}
    for brand, model in db.execute(select(Vehicle.manufacturer, Vehicle.model).where(
            Vehicle.account_id == account_id).distinct()):
        key = canonical.setdefault(brand.casefold(), brand)
        values = catalog.setdefault(key, [])
        if model.casefold() not in {name.casefold() for name in values}:
            values.append(model)
    return {"source": "CarPot curated names + current account vehicles", "complete": False,
            "brands": [{"name": brand, "models": sorted(models, key=str.casefold)}
                       for brand, models in sorted(catalog.items(), key=lambda pair: pair[0].casefold())]}


def automatic_donor_id(db, account_id):
    # Random IDs need no shared sequence or destructive backfill. The existing
    # UNIQUE(account_id, donor_id) remains the final concurrency guarantee.
    for _ in range(5):
        candidate = "AUTO-" + uuid4().hex
        if db.scalar(select(Vehicle.id).where(Vehicle.account_id == account_id,
                                            Vehicle.donor_id == candidate)) is None:
            return candidate
    raise HTTPException(409, "Не вдалося створити унікальний ID. Повторіть спробу.")
