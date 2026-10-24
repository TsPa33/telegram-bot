# Buyers & orders backend (UX 5.2)

Local preparation only. No Railway migration, deployment, new service, Variable
change, production access or provider request is part of this work.

## Architecture and compatibility

`parts.quantity` / `reserved_quantity` remain the authoritative stock quantities;
`operations` remains the stock ledger. New reservations associate ownership with
order lines and link to actual reserve/release/sale Operation IDs. They are not a
second inventory balance. Agreed prices and donor/name snapshots belong to lines;
the sale event freezes them and the buyer/contact snapshot at confirmation. They
never overwrite a Part's current selling price or backfill old transactions.

Models: `buyers`, `orders`, `order_lines`, `order_reservations`, `order_events`,
`order_requests` (technical replay guard). Lines replaced before sale are retained
as inactive versions. Reservation and event history is not deleted or rewritten.
No fabricated buyers, sales, prices, payments or migrations of legacy reserves.

The existing v5 API remains available, including old callers without request keys.
A manual release can only release the unassigned portion of the existing reserve;
assigned units must be released via their order. Direct sale/correction still
cannot consume any reserved stock. The old v5 replay guard is unchanged.

All commands lock the Account with PostgreSQL **FOR NO KEY UPDATE**, then the
Order, then Parts in sorted ID order. This serializes numbering and replay keys
without blocking legacy FK key-share checks while waiting for a Part lock. Every
multi-line command, ledger mutation, event and replay record commits atomically.
Any line failure rolls back the entire command. Different accounts remain scoped
in queries and composite foreign keys; callers cannot supply actor/account IDs.

## API

All paths below have `/api/v1` prefix, require the existing session cookie, and
mutations require `X-CSRF-Token` and the staging frontend Origin. No new CORS or
cookie configuration is required. No new dependencies or API keys are required.

- `POST /buyers`: name, phone, optional additional_phone and notes.
- `GET /buyers?phone=...&offset=0&limit=50`: phone search, including additional phone.
- `GET /buyers/{id}`; `PUT /buyers/{id}`: full buyer replacement with required name/phone.
- `POST /orders`: buyer_id, lines, optional delivery/contact fields, request_key.
- `GET /orders?q=...&phone=...&number=1&status=new&offset=0&limit=50`.
  q matches a number prefix (optional №/#) or normalized phone digits. Explicit
  number is exact. Phone searches include the frozen order contact and the
  buyer's current primary/additional phones. Phone fragments need 3+ digits.
- `GET /orders/{id}`: header, active lines, active reservations, exact string
  totals_by_currency. No mixed-currency total or automatic conversion.
- `PATCH /orders/{id}`: supplied contact/delivery/notes/buyer fields only, request_key.
  Delivery is validated against the merged existing fields. null is rejected;
  use an empty string for optional text. Buyer reassignment is blocked after sale.
- `PUT /orders/{id}/lines`: complete replacement of active lines, request_key.
  Only a new, unsold, unreserved order can change lines. Release first.
- `POST /orders/{id}/reserve`, `/release`, `/sell`, `/cancel`: request_key.
- `POST /orders/{id}/status`: status and request_key; only explicit shipping and
  completion transitions. Other transitions use the dedicated commands above.
- `GET /orders/{id}/events?offset=0&limit=50`: append-only domain history including
  stock Operation IDs, agreed sale lines and explicit status transitions.
- `GET /orders/readiness`: authenticated, read-only contract **6**, required
  revision **d86f21a90b34**, actual database_revisions and feature flags. Returns
  503 on missing tables/columns or a wrong migration head.

Example creation body (use a fresh lowercase UUID per deliberate command):

```json
{
  "request_key": "<UUID>",
  "buyer_id": "<buyer-id>",
  "lines": [
    {"part_id": "<stock-part-id>", "quantity": 1, "unit_price": "123.45", "currency": "UAH"},
    {"part_id": "<other-part-id>", "quantity": 2, "unit_price": "15.01", "currency": "USD"}
  ],
  "delivery_method": "pickup",
  "notes": ""
}
```

Money is Decimal / NUMERIC, serialized as decimal strings. Quantity is 1..1,000,000;
1..100 distinct parts per order. Unit price is required (nonnegative, up to two
fractional digits); never infer an unknown price. Line totals use NUMERIC(20,2).
Each line's currency is explicit. Contact defaults to the buyer at order creation;
subsequent buyer edits do not silently rewrite that frozen contact.

Delivery methods: `pickup` (empty city/address allowed), `branch` (city and branch
in delivery_address), `address` (city and address required). TTN/tracking_number is
optional. No shipment booking or external delivery API call occurs.

Phone formatting is retained for display; normalized digits support search. A
10-digit Ukrainian local number starting with 0 gains 38; leading international
00 is removed. Other numbers are retained as digits without guessing a country.
Normalization is not proof that a phone exists or belongs to the buyer.

Buyer POST/PUT are ordinary CRUD; no deduplication by phone is imposed (shared
family/company numbers are valid). Every order mutation requires request_key.
Reuse the SAME key, endpoint and body after an uncertain/network response. It
returns the original result even after later state changes; GET returns current
state. Reusing the key for another body/order/action returns 409. A new deliberate
command needs a new key. Legacy StockRequest keys and order command keys are
separate namespaces; do not retry an order sale through the manual stock API.

## Lifecycle

- Create: new, no stock mutation, even if a draft asks for more than current stock.
- Reserve: new → reserved; all lines must fit available quantity, atomically.
- Release: reserved → new; releases this order's active reserves only.
- Sell: explicit inventory action for a new/reserved/shipped unsold order. If
  reserved, its reserve is consumed (ledger release + sale in ONE transaction).
  sold_at and line sale_operation_id mark the irreversible sale in this phase.
  A new key cannot sell the same order again. Agreed prices are in line/sale-event
  snapshots; the ordinary stock ledger continues to snapshot the stock card.
- Ship: new/reserved → shipped only after reservation or explicit sale. It changes
  fulfillment status, NOT stock or payment. Tracking number is not mandatory.
- Complete: shipped → completed only after explicit stock sale.
- Cancel: any open unsold order → cancelled, releasing only its active reserves.
  A cancelled request is a no-op on a fresh cancel; other closed-order actions fail.
- Returns/cancelling an already sold order are deliberately rejected pending the
  separately approved returns implementation. No implicit reverse sale is made.

Fulfillment status and sold_at are separate facts: a sold order may still be at
new/reserved until shipped. No status asserts payment. There is no payment module.

## Migration and rollout preparation

Alembic **d86f21a90b34 → down_revision c24a9b71e603**. Adds six tables, indexes and
constraints, plus a unique (id, account_id) key on existing parts for safe composite
foreign keys. It does not update/delete existing rows or attach buyers to old sales.
Creating the Part constraint/index may briefly block writes during migration.
Downgrade is permitted only while buyers/orders/replay tables are empty; once used,
it refuses to destroy business data, assigned reserves or replay evidence.

Existing startup `python -m app.staging` runs Alembic under the migration advisory
lock before Uvicorn. No staging migration has been run as part of this task.
Existing v1–v5 readiness contract numbers/minimum revision remain unchanged; their
actual database_revisions will report the new head. The existing frontend remains
compatible. New order UI must wait for the separate orders/readiness gate.

Future release requires explicit approval: backend-only commit/push (Auto Deploy),
verify ACTIVE and orders/readiness 200 at d86f21a90b34, and run controlled staging
smoke checks before any future frontend rollout. No new Railway service is needed.
Do not rollback to a backend lacking reservation ownership after assigned reserves
are in use: it cannot enforce the guard. Use a compatible rollback or forward fix;
never drop populated order tables or silently turn assigned holds into manual holds.

## Local verification

Use ONLY a disposable PostgreSQL database whose name ends `_test`:

```
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL=<dedicated-local-test-URL> ../.venv/bin/python -m pytest tests unit_tests -q
```

Tests truncate the test database; never point this command at staging/production.
`tests/test_orders.py` covers multi-currency snapshots, lifecycle, legacy reserves,
request replay, simultaneous keys/orders/sales, all-or-nothing rollback, account
isolation/auth/CSRF, delivery validation and upgrade/downgrade data preservation.
