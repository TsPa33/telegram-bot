"""Existing Telegram prices and terms, explicitly versioned. No inferred custom quotes."""

from calendar import monthrange
from datetime import timedelta
from .models import BillingError

# Source: liqpay_callback.py, seller_crm.py and site_packages.py at the verified base.
PRODUCTS = {
    "garage.slots.1": ("garage", 9900, 1, "days30"),
    "garage.slots.5": ("garage", 19900, 5, "days30"),
    "garage.slots.10": ("garage", 29900, 10, "days30"),
    "seller_crm.standard": ("seller_crm", 9900, 0, "days30"),
    "site.standard": ("site", 49900, 0, "year"),
    # A project quote is required for Plus/custom: fulfillment and renewal terms are not explicit.
}


def seed(c):
    for sku, (product, amount, capacity, cadence) in PRODUCTS.items():
        c.execute(
            "INSERT INTO billing.plan_versions VALUES (%s,1,%s,'base',%s,'UAH',%s,0) ON CONFLICT DO NOTHING",
            (sku, product, amount, capacity),
        )
        c.execute(
            "SELECT * FROM billing.plan_versions WHERE sku=%s AND version=1", (sku,)
        )
        row = c.fetchone()
        if (row["product"], row["amount_minor"], row["vehicle_capacity"]) != (
            product,
            amount,
            capacity,
        ):
            raise BillingError("Immutable product catalogue drift")
        c.execute(
            "INSERT INTO billing.product_terms VALUES (%s,1,%s,%s) ON CONFLICT DO NOTHING",
            (
                sku,
                cadence,
                "Verified legacy source at b45d3789f4ec7da267da60779cad489866dbb4b6",
            ),
        )


def period_end(c, plan, start):
    c.execute(
        "SELECT cadence FROM billing.product_terms WHERE sku=%s AND version=%s",
        (plan["sku"], plan["version"]),
    )
    terms = c.fetchone()
    if not terms:
        raise BillingError("Approved product terms required")
    if terms["cadence"] == "days30":
        return start + timedelta(days=30)
    if terms["cadence"] == "year":
        return start.replace(
            year=start.year + 1,
            day=min(start.day, monthrange(start.year + 1, start.month)[1]),
        )
    raise BillingError("Quoted perpetual fulfillment is not self-service")


class LegacyMigration:
    """Read-only preview accepts exported metadata, never trusts a legacy success as proof."""

    def __init__(self, db):
        self.db = db

    def preview(self, peer, rows):
        seen = set()
        result = []
        with self.db.transaction() as c:
            for row in rows:
                order = row.get("order_id")
                duplicate = not isinstance(order, str) or not order or order in seen
                seen.add(order)
                c.execute(
                    "SELECT invoice_id,settlement_id FROM billing.legacy_mappings WHERE peer=%s AND legacy_order=%s",
                    (peer, order or ""),
                )
                mapped = c.fetchone()
                result.append(
                    dict(
                        legacy_order=order,
                        duplicate=duplicate,
                        mapped=dict(mapped) if mapped else None,
                        decision="review"
                        if duplicate
                        else "already_mapped"
                        if mapped
                        else "provider_verification_required",
                    )
                )
        return result

    def map_verified(self, peer, legacy_order, invoice, settlement, evidence):
        # Only operational LiqPay evidence already verified by the canonical payment boundary.
        with self.db.transaction() as c:
            c.execute(
                "SELECT s.id FROM billing.settlements s JOIN billing.intents n ON n.id=s.intent_id JOIN billing.provider_orders o ON o.intent_id=n.id JOIN billing.provider_evidence e ON e.order_id=o.order_id WHERE s.id=%s AND s.invoice_id=%s AND n.environment=%s AND n.provider='liqpay' AND e.digest=%s AND e.classification='success' AND e.payment_id=s.transaction_id",
                (settlement, invoice, self.db.environment, evidence),
            )
            if not c.fetchone():
                raise BillingError("Verified provider evidence required")
            c.execute(
                "INSERT INTO billing.legacy_mappings(peer,legacy_order,invoice_id,settlement_id,evidence_id) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (peer, legacy_order, invoice, settlement, evidence),
            )
            c.execute(
                "SELECT invoice_id,settlement_id,evidence_id FROM billing.legacy_mappings WHERE peer=%s AND legacy_order=%s",
                (peer, legacy_order),
            )
            row = c.fetchone()
            if not row or tuple(row.values()) != (invoice, settlement, evidence):
                raise BillingError("Conflicting legacy mapping")
