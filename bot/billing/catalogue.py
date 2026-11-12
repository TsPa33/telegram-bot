from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from types import MappingProxyType
import calendar
from .models import BillingError, PlanVersion, Quote

CATALOGUE = MappingProxyType(
    {
        p.sku: p
        for p in (
            PlanVersion("warehouse.standard", 1, "warehouse", 100_000, 10, 5),
            PlanVersion("warehouse.premium", 1, "warehouse", 450_000, 50, 10),
            PlanVersion("warehouse.slots.1", 1, "warehouse", 30_000, 1, 0, "addon"),
            PlanVersion("warehouse.slots.5", 1, "warehouse", 120_000, 5, 0, "addon"),
            PlanVersion("warehouse.slots.10", 1, "warehouse", 200_000, 10, 0, "addon"),
        )
    }
)


def monthly_end(start: datetime) -> datetime:
    """One base invoice period; recurring anchor restoration belongs to the scheduler."""
    if start.tzinfo is None or start.utcoffset() is None:
        raise BillingError("Timezone-aware date required")
    start = start.astimezone(timezone.utc)
    month = start.month % 12 + 1
    year = start.year + (start.month == 12)
    return start.replace(
        year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1])
    )


def money_minor(value: str) -> int:
    """Reject floats, non-finite amounts and fractional kopecks at money boundaries."""
    if not isinstance(value, str) or len(value) > 128:
        raise BillingError("Money must be a decimal string")
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount > Decimal("90000000000000"):
            raise BillingError("Invalid money")
        if amount and amount < Decimal("0.01"):
            raise BillingError("Positive money must be at least one kopeck")
        with localcontext() as context:
            context.prec = 160
            minor = amount * 100
            if minor != minor.to_integral_value():
                raise BillingError("Fractional kopecks")
        result = int(minor)
        if result > 9_000_000_000_000_000:
            raise BillingError("Money exceeds supported range")
        return result
    except (ArithmeticError, ValueError) as exc:
        raise BillingError("Invalid money") from exc


def quote(
    plan: PlanVersion,
    start: datetime,
    end: datetime,
    effective_at: datetime,
    quantity: int = 1,
) -> Quote:
    if (
        type(plan.amount_minor) is not int
        or plan.amount_minor <= 0
        or plan.currency != "UAH"
    ):
        raise BillingError("Invalid plan price")
    if type(quantity) is not int or not 1 <= quantity <= 1000:
        raise BillingError("Invalid quantity")
    if any(
        t.tzinfo is None or t.utcoffset() is None for t in (start, end, effective_at)
    ):
        raise BillingError("Timezone-aware dates required")
    start, end, effective_at = (
        t.astimezone(timezone.utc) for t in (start, end, effective_at)
    )
    if not start <= effective_at < end:
        raise BillingError("Quote outside period")

    def micros(delta):
        return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds

    full = plan.amount_minor * quantity
    with localcontext() as context:
        context.prec = 80
        due = (
            Decimal(full) * micros(end - effective_at) / micros(end - start)
        ).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return Quote(
        plan.sku,
        plan.version,
        quantity,
        full,
        int(due),
        plan.currency,
        effective_at,
        end,
    )
