# UI-5 — Sales journal

## Audit / support matrix (before implementation)

Base: `80adb5af3fcc80e472d65bf02ca6c8681277cb68`. `SalesLedger` renders `/sales` inside the existing Workshop readiness gate. `SalesWorkspace` owns quick sale confirmation/CAS/replay handling; Operations is the existing advanced stock workflow; Orders owns reserve/sell and commercial snapshots. They are not being rewritten.

| Feature | Existing support | UI-5 decision |
| --- | --- | --- |
| Quick sale | Search → existing operation confirmation, `sales.create` | Link to existing search, also requires `inventory.view` |
| Order sale | Existing order workflow, `orders.fulfill` + `sales.create` | View-only link to existing order if `orders.view` |
| Ledger | `GET /sales`, `sales.view`, one stock-sale operation per row | Compact table / cards |
| Period, vehicle, source, name/OEM/article | Server filters on immutable operation snapshot | Keep server filtering, 50/page |
| Buyer / employee | Nullable API snapshot/name fields | Display known values; no fabricated identities |
| Historical money | `unit_price`, `total`, `currency`, `price_recorded`; `sales.view_financials` | Never substitute current Part price |
| Operation number / payment state | Not supplied by sales API | No fake columns or filters |
| Full filtered totals / units | Not supplied by `/sales`; only overall operation count | Explicit page-scoped amount/average/unit cards on multiple pages |
| `/sales/summary` | Dates only; extra analytics permissions; no q/vehicle/source | Do not misuse this as a fully filtered summary |
| Refund / sale cancellation / print | No supported ledger operation | No active controls |
| Details | Current list fields include donor, note, order_id, buyer, actor | Existing Modal rendered as a compact read-only drawer, no new endpoint |

All changes and QA are local. No push/deployment, production, backend, migration or existing warehouse data changes are authorized.

## Final implementation

The supplied standalone UI-5 image was unavailable, so the written layout specification was used. The journal now has a compact header, existing “Швидкий продаж” navigation, inline server filters, four scoped indicators, a desktop table and a single responsive DOM representation as cards at ≤1000px. iPhone keeps the period visible and collapses the remaining filters. Names clamp to two lines with full text in the read-only detail panel. No photographs, operation numbers, payment states or customer identities are invented.

`SalesLedger.tsx` retains the existing API, loader and Workshop/RBAC gate; `sales-ui5.css` scopes the new geometry to this page and its drawer. `salesLedgerPresentation.ts` contains display-only query/decimal helpers. Reused components include `Pager`, `State`, `Empty`, native `Modal`, `useLoad`, `money`, `when`, `useCan`, React Router `Link`, Lucide icons and UI-1 tokens. Existing SalesWorkspace, Operations, Inventory, Orders, App routes, sidebar, tokens, API client and backend files are unchanged.

The drawer uses the existing native modal's focus trap, Escape/backdrop behavior and a page-local return-focus handler. No second modal or new endpoint is introduced. It shows only fields already supplied in the selected ledger row; the existing order link is permission-gated. Donor fallback is explicitly labelled current data when the API has no historical donor snapshot.

## Historical financial data and summary scope

- Row unit price/total come only from `/sales`. No current Part price or current order-line price is substituted. Legacy order fallback remains the backend's existing sale-confirmed event projection.
- A single row remains one stock sale operation. Multiple lines of one order are not collapsed into a fabricated “transaction/order count”. The count card uses the server's filtered `total`; units are the sum of `quantity` for the displayed operations.
- Amount and average cards are split by original UAH/USD currency, with no conversion or profit claim. The average is per priced sale operation within that currency, not a weighted unit price. Decimal display sums use integer cents, preserving precision; historical amounts are not recomputed from current prices.
- Unknown/malformed/redacted prices remain unknown, never zero. A genuine recorded zero participates in the average. Unpriced operations still contribute known quantities; their exclusion from amounts/averages is stated.
- If all filtered operations fit on the page, the cards cover the complete result. Otherwise labels explicitly say “на сторінці” and the note gives the page count versus total. No whole-period financial total is claimed from one page. `/sales/summary` is not called because it cannot apply the journal's query/donor/source filters and requires extra analytics permissions.
- Without `sales.view_financials`, amount/average values and drawer prices are hidden; no totals are reconstructed from other fields. `sales.view` remains required for the route and API. Quick sale navigation also requires `sales.create` and `inventory.view`; order links require `orders.view`.

Future backend tasks, outside UI-5: fully filtered aggregate endpoint, domain payment fields/filters, documented operation numbering, explicit audited refund/reversal workflow and supported print/export. No active placeholder controls for these were added.

## Local verification and fixture

Build **PASS**; full frontend suite **442 PASS / 0 FAIL**. UI-5 browser QA **PASS** at 1440/1280/1000/900/768/390/375px. Independent state/permission harness **PASS**. UI-3 and UI-4 regression scripts also **PASS** at all seven widths. No critical JS errors or horizontal overflow were observed.

The only new database is the fresh, isolated local `warehouse_ui5_test`. `tests/seed-ui5.py` accepts only that loopback database name and refuses an existing database. It initializes the unchanged existing migrations solely for test infrastructure and inserts explicit synthetic fixtures: 126 historical operations, quick/order sources, two donors, a buyer, known UAH/USD/zero/missing prices, legacy order-event prices, read-only/blocked users and a foreign workspace. It does not reset, clone, alter or reseed existing Warehouse databases. No new migration file was created.

For the legacy example, the API records a 5.00 USD unit price / 10.00 USD total while the current Part price is 999.99 UAH and the linked current order line is 99.00 USD per unit. Browser tests verify that the journal/drawer still show the historical 10.00 USD, not either mutable price. The foreign workspace's synthetic operation never appears in the owner's 126 rows.

Production preview: local API 8031, frontend 5205. UI-3/UI-4 regressions use their existing isolated local synthetic API 8030/preview 5203, without writes. No real Volvo catalogue data, Railway or staging acceptance is claimed. All browser journal requests are GET-only; complete sales, parts and linked order API snapshots are compared before/after. Fixture construction is separate from this read-only acceptance.

Commands from `warehouse/frontend`:

```
npm run build
node --test tests/*unit.mjs
WAREHOUSE_E2E=1 node tests/ui5-browser.mjs
WAREHOUSE_E2E=1 node tests/ui5-states-browser.mjs
WAREHOUSE_E2E=1 node tests/ui3-browser.mjs
WAREHOUSE_E2E=1 node tests/ui4-browser.mjs
```

Test infrastructure: PostgreSQL on loopback, Python Warehouse dependencies, Chromium and frontend dependencies. A fresh fixture is created with `WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_ui5_test /workspace/.venvs/warehouse/bin/python tests/seed-ui5.py`. Start the unchanged API with this database URL, cookie secure false and catalogue worker disabled, then `WAREHOUSE_API_PROXY=http://127.0.0.1:8031 npm run preview -- --port 5205` after building. Scripts require `/tmp/ui5-fixture.json` and the synthetic owner's local storage state at `/tmp/ui5-owner-session.json`; these credentials/sessions are test-only and not committed. `ui5-before.mjs` captured baseline screenshots and initialized that local owner session before UI edits. Read-only/blocked/foreign login in the state harness uses only the freshly seeded synthetic accounts.

The state harness mocks only delays, 503 and network timeout to verify loading, stale response rejection, hiding old totals on error, preserving the query on retry and recovery from an invalid date range. Normal search, period/source/vehicle pagination, financial values and permission checks use the actual local backend. Keyboard Enter opens the drawer; Escape restores focus to the invoking button.

Known limits: financial/quantity summary cards cover only a page for multi-page results; native date bounds retain the original browser-local timezone semantics; the existing >500 kB Vite bundle warning remains; viewport Chromium QA does not replace physical iPhone Safari acceptance. A filter/query change intentionally hides old rows while new results load. No global redesign or backend regression suite was run.

## Screenshots

All screenshots are actual browser captures of the same synthetic fixture, not design mockups.

- [Desktop before](screenshots/sales-before-1440.png)
- [Desktop after / journal](screenshots/sales-after-1440.png)
- [iPhone before](screenshots/sales-before-390.png)
- [iPhone after](screenshots/sales-after-390.png)
- [iPhone 375px](screenshots/sales-after-375.png)
- [Sale detail panel](screenshots/sales-details-1440.png)
- [Mobile detail panel](screenshots/sales-details-390.png)
- [Mobile filters](screenshots/sales-filters-390.png)
