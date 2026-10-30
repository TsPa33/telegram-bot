# R4 — Multi-item Orders

## Scope and model

Reuses `Order`, active `OrderLine` (maximum 100 distinct parts), `OrderReservation`, immutable `OrderEvent` and `OrderRequest`. There is no new status system, sales mechanism, database table or migration. Delivery completion and the recorded sale (`sold_at`) remain separate.

The existing `/orders` POST saves an unfinished order without a stock movement. PUT `/orders/{id}/lines` replaces active lines only on a new, unsold, unreserved order. Users can reopen `/orders/{id}`, choose “Змінити позиції”, add/remove lines and change agreed quantities/prices. Release an existing reservation explicitly before editing. Sold line amounts cannot be edited.

The form uses the shared modal/focus behavior. Desktop has stock search on the left and basket/customer/delivery/totals on the right; mobile stacks them without losing React form state. Search is server-paginated (50), supports name/OEM/article and donor, shows available units, and prevents adding a duplicate or more than 100 parts. An empty donor filter is omitted, not sent as a blank foreign key. No fake images.

`GET /orders/{id}` adds `current_part` only for users with `inventory.view`, in one tenant-bound query. It contains current OEM and free units, advisory rather than a reservation. It does not change historical prices or persist inventory data in an idempotent response. Legacy orders without these fields remain valid. Authoritative quantities are checked again in the server transaction.

## Actor / buyer / currencies

The current authenticated employee is shown as manager. Actual actors are derived by the server and recorded in events; there is no existing permission/model for assigning another actor, so the form does not impersonate another manager. Extra manager/actor fields are rejected. Existing buyer search and phone normalization are reused. No new personal data is required.

Each line carries an explicit agreed price and UAH or USD. Zero is a real price; blank is invalid. Line and basket totals use integer cents (`BigInt`), then strings, with independent currency totals. No exchange rate or current Part price replaces the agreed price. Incomplete inputs show an explicit incomplete-total notice.

## Atomicity, stock and retry

Unchanged domain command: workspace account lock (`NO KEY UPDATE`), order lock and sorted part row locks, all line operations and audit events within a single transaction/commit. Reservation and sale use the existing stock domain function. A failing later line rolls back the earlier line, audit, financial snapshots, reservations and request record. No frontend loop of individual sales.

Existing OrderRequest fingerprints actor/scope/body. A replay uses the same request key/body and returns the original response; a different key cannot sell an already sold order. `useOrderRequests` persists uncertain commands in sessionStorage, suppresses duplicate submission and offers only an explicit recovery action in the center. There is no automatic retry/sale on reload. A successful creation followed by failed reservation remains a saved order, with an explicit reservation warning.

Quick Sale, existing orders, immutable sale operations, historical ledger/analytics, permissions and workspace isolation are preserved. OEM in the editor is live reference metadata, not a claimed historical OEM snapshot.

## Verification

- PostgreSQL: 46 passed (`test_orders.py`, `test_sales_center.py`, `test_workshop.py`, `test_sales_analytics.py`). Includes one/multiple lines, same/different donors, competing reservations, same/different-key races, insufficient stock, actor/CSRF/RBAC/workspace checks, historical price changes, mixed currencies, missing prices, migration preservation, and deliberately injected failure after the first stock write with full rollback.
- Frontend build passed; complete unit suite: 447 passed. Five new tests cover exact decimal arithmetic, large totals, zero/missing prices, command payload and validation.
- Actual local PostgreSQL browser QA: 1440/1280/1000/900/768/390/375px; isolated synthetic workspace in `warehouse_r34_test`, never staging. Covers OEM/donor search, add/remove/re-add, quantities/prices/currency totals, no movement on draft, reload/edit, explicit confirmation, disabled reconfirmation, no horizontal overflow and no JS errors.
- Additional browser cases: remove a line from a saved draft then add it back; injected HTTP 409 preserves entered price; lost creation response at 375px; lost successful sale response at 390px; reload and explicit same-key replay recover the same order without extra stock movement.
- R3 compatibility regression: UI-3/UI-4/UI-5 at seven widths; R1 at six widths, all passed. R4 changes no stock/sales algorithm. Full backend regression outside these affected domains was not run.

Screenshots use synthetic data only:

- [Desktop composer](composer-desktop.png)
- [Mobile picker and basket](composer-mobile-top.png)
- [Mobile buyer / totals](composer-mobile-bottom.png)

All seven-width evidence and JSON results: `/workspace/scratch/r4` (regenerated by `WAREHOUSE_E2E=1 node tests/r4-browser.mjs`). The script explicitly requires the local synthetic database fixture marker. Authentication storage remains outside git.

## Release limitations and safe staging procedure

No push, deployment or staging acceptance has occurred. Browser writes were only against newly created synthetic actors/donors/parts. Existing real Volvo donors, inventory, finance and production were not accessed or changed.

After a separate release authorization: fetch the exact feature branch, verify fast-forward and `/warehouse` diff, then push normally. No migration is needed (head remains `b7e14d90c2f6`). Verify API/Web commit, health and read-only journal first. Only use a designated synthetic staging workspace with owner approval for create/reserve/sell acceptance. Never test sales on existing real stock. Do not run catalogue import, canonical publication, backfill or automatic receipts.

An unsaved form is in-memory; close/reload can discard it. Save an unfinished server order to resume later. Only uncertain transmitted commands are persisted for recovery. Availability is advisory until reserve/confirm. No other-manager assignment is introduced.
