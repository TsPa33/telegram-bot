"""Read-only reference access. Model grouping never establishes year fitment."""
from sqlalchemy import select, func, and_
from sqlalchemy.orm import aliased
from app.models import Category
from app.models.aleto import AletoModel, AletoOffer, AletoPrice, AletoApplication, AletoTaxonomy
from app.services.aleto_import import identity


def model_for_vehicle(db, vehicle, account_id):
    # Compare full names only; no substring, generation, year or VIN inference.
    return next((r for r in db.scalars(select(AletoModel).where(AletoModel.account_id == account_id))
                 if identity(r.manufacturer) == identity(vehicle.manufacturer) and identity(r.model) == identity(vehicle.model)), None)


def potential_types(db, vehicle, account_id):
    model = model_for_vehicle(db, vehicle, account_id)
    if model is None:
        return []
    root, sub = aliased(Category), aliased(Category)
    rows = db.execute(select(root, sub).join(AletoTaxonomy, AletoTaxonomy.category_id == root.id)
                      .join(sub, AletoTaxonomy.subcategory_id == sub.id).where(
                          AletoTaxonomy.account_id == account_id, AletoTaxonomy.model_id == model.id,
                          root.account_id == account_id, sub.account_id == account_id,
                          root.archived.is_(False), sub.archived.is_(False),
                          AletoTaxonomy.normalization_status == 'verified').distinct())
    # One potential type per verified subcategory, NOT one per source offer.
    # Explicit opt-in prevents reference alternatives becoming stock by default.
    return [dict(source='aleto.v1', catalog_key=sub.id, category_key=root.id, category_name=root.name,
                 subcategory_key=sub.id, subcategory_name=sub.name, name=sub.name, position='', included=False)
            for root, sub in rows]


def catalogue(db, vehicle, account_id, *, offset=0, limit=50, category_id=None, subcategory_id=None, q=''):
    model = model_for_vehicle(db, vehicle, account_id)
    empty = dict(items=[], total=0, offset=offset, limit=limit, categories=[],
                 year_compatibility='unverified', source='Aleto', price_label='Ціна Aleto (орієнтир)')
    if model is None:
        return empty
    paths = select(AletoTaxonomy).where(AletoTaxonomy.account_id == account_id, AletoTaxonomy.model_id == model.id)
    if category_id:
        paths = paths.where(AletoTaxonomy.category_id == category_id)
    if subcategory_id:
        paths = paths.where(AletoTaxonomy.subcategory_id == subcategory_id)
    matching = paths.with_only_columns(AletoTaxonomy.offer_id).distinct()
    stmt = select(AletoOffer).where(AletoOffer.account_id == account_id, AletoOffer.id.in_(matching))
    if q.strip():
        stmt = stmt.where((AletoOffer.title.ilike('%' + q.replace('%', r'\%').replace('_', r'\_') + '%', escape='\\')) |
                          (AletoOffer.source_article == q.strip()) | (AletoOffer.oem == q.strip()))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = db.execute(stmt.add_columns(AletoPrice).join(AletoPrice, and_(AletoPrice.offer_id == AletoOffer.id,
                           AletoPrice.account_id == account_id, AletoPrice.observed_at == AletoOffer.observed_at))
                      .order_by(AletoOffer.source_article).offset(offset).limit(limit))
    items = [dict(id=o.id, article=o.source_article, title=o.title, oem=o.oem, condition=o.condition,
                  price_uah=p.price_uah, price_usd=p.price_usd, observed_at=p.observed_at,
                  source_url=p.source_url) for o, p in rows]
    root, sub = aliased(Category), aliased(Category)
    nodes = db.execute(select(root.id, root.name, sub.id, sub.name).join(AletoTaxonomy, AletoTaxonomy.category_id == root.id)
                       .outerjoin(sub, AletoTaxonomy.subcategory_id == sub.id).where(
                           AletoTaxonomy.account_id == account_id, AletoTaxonomy.model_id == model.id,
                           root.account_id == account_id, root.archived.is_(False)).distinct()
                       .order_by(root.name, sub.name))
    return {**empty, 'items': items, 'total': total,
            'categories': [dict(category_id=c, category_name=n, subcategory_id=s, subcategory_name=sn) for c, n, s, sn in nodes]}
