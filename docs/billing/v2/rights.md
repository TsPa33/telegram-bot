# Product policy and archive invariants

Warehouse business model implemented in the isolated pilot:
Standard 1000 UAH/month, 10 active donors, owner + 5 active employees.
Premium 4500 UAH/month, 50 donors, owner + 10 employees. Monthly add-ons +1/300,
+5/1200, +10/2000 UAH; proportional quote to base period end. No quota accumulation.

## Time-based rights

Paid base windows -> ACTIVE, then 72-hour GRACE anchored at paid end, then EXPIRED.
Trial -> TRIAL for exactly 10 x 24h, then EXPIRED without grace. Future windows do
not grant current access. Add-on capacity applies only inside its own interval and
with an effective base right. Free is no effective/prior period. Over-limit is an
orthogonal usage state, never a source of paid rights. No automatic staff deactivation.

| Operation | Compatibility/OFF | Free / Expired | Trial / Active / Grace | Paid over-limit |
|---|---|---|---|---|
| Login, security, view/search/history | existing RBAC | existing RBAC | existing RBAC | existing RBAC |
| Existing GET exports | existing RBAC | allowed by RBAC | allowed by RBAC | allowed by RBAC |
| New donor / restore | unchanged | blocked | capacity guard | blocked if increasing over limit |
| New inventory / dismantling / new order | unchanged | blocked | allowed by RBAC | existing donors may work/sell |
| New/reactivated employee | unchanged | blocked | seat guard | no increases beyond limit |
| Old order completion/reserve/sell/status | unchanged | only order created before expiry cutoff | existing RBAC | existing RBAC |
| Replace/add/increase old order lines | unchanged | blocked | existing RBAC | existing RBAC |
| Release / cancel old obligation | unchanged | allowed by RBAC | existing RBAC | existing RBAC |
| Genuine return against stock sale | new endpoint OFF | permitted with provenance, bounded quantity, idempotency | same | may create over-limit; never drop physical stock |
| Billing/trial/sync/quote | new pilot OFF | owner only | owner only | owner only |

No blanket mutation paywall is used for enrolled Phase 2 workspaces. Unknown write
operations fail closed on expiry; read-only recovery POSTs are explicit exceptions.
Employees never gain payment/bonus/payout management from a product subscription.
Existing system currently has no invitation workflow; no imaginary invitation seats
are counted. Any future invitation acceptance must use the same quota boundary.

## Garage and archive

An unarchived donor occupies one place, even with no dismantling yet. An archived
donor with quantity/reservation occupies a place regardless of Part.archived or
assortment_enabled. Immutable donor provenance is included in usage. Hiding a part
never frees a place. Detaching/changing a donor link after enrollment is rejected.
New and restored Vehicle objects, both actual create entry points (ordinary/VIN
and global catalogue) and direct ORM batch inserts pass one Session before_flush
quota guard. The existing model-directory import creates variants, not Vehicle rows.

A workspace row lock serializes last-place and team-seat allocation. The guard checks
pending in-memory changes plus committed usage in the same transaction. With two
requests for the last place only one commits. Owner itself does not consume a seat.
Direct SQL/admin writers are trusted infrastructure, not supported import entry points;
future donor import must use the same service/ORM guard and a reviewed batch contract.

Archive operation checks every donor part's physical quantity and reserve, including
hidden/archived parts. Positive stock blocks closure; zero-stock closure keeps donor,
parts, photos, operations and orders. Restore consumes capacity. Genuine post-sale
returns may revive physical stock against an archived donor: it occupies capacity and
may produce over-limit, without deleting stock or fabricating a new purchase.

Return evidence is linked to immutable sale Operation, cannot exceed sold quantity
across all returns, is account scoped and request-key idempotent. It adds a new return
operation; original sale is untouched. This is an inventory return, not a financial
refund or LiqPay reversal. Money/refund accounting remains a Phase 3+ gate.

## Recommendations still requiring final owner approval

Detailed grace rights, trial tariff switching policy, add-on billing integration,
upgrade proration credits, organization duplicate detection and production enrollment
must be ratified before any real workspace rollout. No fixture grant proves payment.
