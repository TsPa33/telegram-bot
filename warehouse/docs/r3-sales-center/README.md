# R3 — Unified Sales Center

## Architecture audit before changes

Base: `41d6c8d798568d05572e6e3ca2281c8b04af417b`; Alembic head `b7e14d90c2f6`.

| Feature | Existing implementation | Required change / risk |
| --- | --- | --- |
| Multi-item order | Order + active OrderLine, up to 100 distinct parts | Reuse; no duplicate tables |
| Reservation / confirmation | orders.command → account/order/sorted part locks → one commit | Reuse; never sell each line from frontend |
| Retry protection | OrderRequest, actor/scope/body fingerprint + persisted client request | Reuse |
| Quick sale | stock operation with commercial/actor snapshots | Preserve |
| Historic money | Operation.after.sale; legacy OrderEvent fallback | Share existing projection, never current Part price |
| Manager | Operation.actor_id / actor_identity; OrderEvent created actor | Reuse actual actor, no assigned-manager fiction or backfill |
| Orders filters | Existing phone/number/status; paginated | Center adds bounded SQL period/actor/vehicle search |
| Sales filters | Existing period/source/part search | Center adds actor/phone/order number, tenant-bound |
| Phone permission | orders.view reads buyer/order contacts | Enforce explicitly in mixed journal; reject unauthorized phone filter |
| Unified journal | Not present | Paginated UNION of distinct order/sale rows, explicit order link, no revenue sum across both |
| Analytics | /sales/summary, exact history-based SQL totals | Reuse independent analytic period; optional actor predicate, no page sums |
| Roles / workspace | Server-derived Identity, central route registry, CSRF | Preserve; only scoped read routes added |

R4 is safe to proceed using the existing transaction model. No migration is required for either stage. Manager means the actual creator/confirming actor, not an assignable contact; no existing permission supports acting as another manager, so actor spoofing/assignment is not introduced.

## Verification

- PostgreSQL: `test_sales_center.py`, `test_workshop.py`, `test_sales_analytics.py`: 25 passed. Tests cover tenant scope, sales-only/orders-only/denied users, contact redaction, phone normalization, actual/inactive/renamed actors, links, filters, pagination and historical aggregates.
- Frontend: build passed; `node --experimental-strip-types --test tests/*unit.mjs`: 442 passed.
- `WAREHOUSE_E2E=1 node tests/r3-browser.mjs`: passed at 1440/1280/1000/900/768/390/375px against disposable `warehouse_r34_test`, with zero domain writes and zero JS errors. Screenshots: `/workspace/scratch/r3/center-{width}.png`.
- The old UI-5 ledger remains available at `/sales?view=ledger`; its browser regression explicitly uses that compatibility URL. `/orders` redirects to the center, `/orders/:id` keeps the existing detail view.
- Uncertain order commands remain visible in the center and can only be explicitly retried with their original request body/key; a new order is disabled until resolved.
- No schema migration, backfill, price/stock/finance write or staging access. Analytics uses its own period/manager filters; journal status counts use the full filtered order scope, not the page. Sold status and delivery status remain distinct.

## Local reproduction / release

Run API against a disposable migrated PostgreSQL database and Vite preview with the same-origin API proxy. Fixture scripts must only target their explicitly named local test database. Browser credentials and storage states stay in `/tmp`, outside git.

For a later authorized staging release: fetch and verify the feature branch ancestry; review the two commits and `/warehouse` scope; use ordinary fast-forward push only. No migration is added here. Verify API/Web startup, role-specific journal and existing order deep links using read-only staging acceptance. Do not create sales on real data for acceptance.

Compatibility browser regressions: UI-3 and UI-4 at 1440/1280/1000/900/768/390/375px; UI-5 at those same seven widths; R1 at 1440/1280/900/768/390/375px. No domain writes were performed by these read-only suites.
