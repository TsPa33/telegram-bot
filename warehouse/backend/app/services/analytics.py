from decimal import Decimal
from sqlalchemy import select, func
from app.models import Category, Operation, Part, Vehicle
from app.services.inventory import snapshot


def dashboard(db, account_id, vehicle_id=None):
    filters = [Part.account_id == account_id, Part.archived.is_(False)]
    if vehicle_id:
        filters.append(Part.vehicle_id == vehicle_id)
    expr = lambda e: func.coalesce(func.sum(e), 0)
    totals = db.execute(
        select(
            func.count(Part.id),
            expr(Part.quantity),
            expr(Part.quantity - Part.reserved_quantity),
            expr(Part.reserved_quantity),
            func.coalesce(func.sum(Part.quantity * Part.selling_price).filter(Part.currency=="UAH"),0),
            expr(Part.quantity * Part.unit_cost),
            func.coalesce(
                func.sum((Part.selling_price - Part.unit_cost) * Part.quantity).filter(
                    Part.unit_cost.is_not(None), Part.selling_price.is_not(None), Part.currency=="UAH"
                ),
                0,
            ),
            func.count(Part.id).filter(
                Part.unit_cost.is_not(None), Part.selling_price.is_not(None), Part.currency=="UAH"
            ),
        ).where(*filters)
    ).one()
    vf = [Vehicle.account_id == account_id, Vehicle.archived.is_(False)]
    if vehicle_id:
        vf.append(Vehicle.id == vehicle_id)
    vcount, vcost = db.execute(
        select(func.count(Vehicle.id), expr(Vehicle.acquisition_cost)).where(*vf)
    ).one()
    categories = db.execute(
        select(Category.name, expr(Part.quantity))
        .select_from(Part)
        .outerjoin(Category, Part.category_id == Category.id)
        .where(*filters)
        .group_by(Category.id, Category.name)
    ).all()
    conditions = db.execute(
        select(Part.condition, expr(Part.quantity))
        .where(*filters)
        .group_by(Part.condition)
    ).all()
    vehicles = db.execute(
        select(Vehicle.id, Vehicle.donor_id, expr(Part.quantity * Part.selling_price))
        .select_from(Part)
        .join(Vehicle, Part.vehicle_id == Vehicle.id)
        .where(*filters,Part.currency=="UAH")
        .group_by(Vehicle.id)
    ).all()
    vehicle_values = db.execute(
        select(Vehicle.id, Vehicle.manufacturer, Vehicle.model, Vehicle.year, Vehicle.number,
               Part.currency, expr(Part.quantity * Part.selling_price))
        .select_from(Part).join(Vehicle, Part.vehicle_id == Vehicle.id)
        .where(*filters).group_by(Vehicle.id, Part.currency)
        .order_by(Vehicle.manufacturer, Vehicle.model, Vehicle.id, Part.currency)
    ).all()
    recent = list(
        db.scalars(
            select(Operation)
            .where(
                Operation.account_id == account_id,
                *([Operation.vehicle_id == vehicle_id] if vehicle_id else []),
            )
            .order_by(Operation.created_at.desc(), Operation.id)
            .limit(8)
        )
    )
    valuations=db.execute(select(Part.currency,func.coalesce(func.sum(Part.quantity*Part.selling_price),0)).where(*filters).group_by(Part.currency)).all()
    return dict(
        valuation_by_currency=[{'currency':currency,'value':str(value)} for currency,value in valuations],
        vehicles=vcount,
        positions=totals[0],
        stock_units=totals[1],
        available_units=totals[2],
        reserved_units=totals[3],
        estimated_sales_value=totals[4],
        allocated_parts_cost=totals[5],
        potential_gross_margin=totals[6] or Decimal(0),
        margin_positions=totals[7],
        vehicle_acquisition_cost=vcost,
        by_category=[
            {"name": n or "Без категорії", "quantity": q} for n, q in categories
        ],
        by_condition=[{"name": n, "quantity": q} for n, q in conditions],
        vehicle_valuation_by_currency=[
            {'id':i,'name':f'{brand} {model} · {year} · №{number}', 'currency':currency,'value':str(value)}
            for i,brand,model,year,number,currency,value in vehicle_values
        ],
        by_vehicle=[{"id": i, "name": n, "value": v} for i, n, v in vehicles],
        recent_operations=[snapshot(r) for r in recent],
    )
