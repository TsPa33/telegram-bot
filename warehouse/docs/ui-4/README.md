# UI-4 — Parts search

Frontend-only redesign on base `ae9fb1b7d4626b8494e92a39e963e75835b7ed5c`. No push, deployment, backend or database schema changes. No data mutations were performed during UI-4 QA.

## Audit and scope

`App.tsx` mounts the same quick `SalesWorkspace` at `/` (the navigation destination) and compatibility alias `/search`. `pages/Catalog.tsx` manages category/global catalogue browsing, not warehouse parts search; it is unchanged. The former quick workspace rendered a large heading, separate mode/explanation blocks, a filter panel before the search input, and duplicated desktop/mobile results. This placed results unnecessarily low.

The new compact heading has the requested subtitle and mode switch. Search plus “Знайти” precedes a compact filter row. Desktop uses the existing UI-3 row hierarchy; tablet/iPhone uses the same data in cards with collapsed filters. Touch suggestions stay in flow on mobile so they cannot cover the filter toggle. Styling is scoped to `.ui4-*`; UI-1 tokens, UI-2 sidebar and UI-3 inventory layouts are unchanged. The separate approved UI-4 image was unavailable, so the supplied written layout specification was used.

## Reuse and preserved behavior

- `InventoryPartRow` / `InventoryTableHead`: shared compact rows with optional photo/extra metadata slots; defaults unchanged for UI-3.
- `PriceSummary`, `useMarketPrices`, `SellerPriceEditor`: existing A recommendation vs B/C similar-price semantics, original currencies, no supplier branding or conversion. Market reads are bounded to the current 50 results.
- Existing `PartActions`, price dialog, sale/stock `OperationDialog`, notes/inspection/history/edit/archive controllers and permission guards. Sale still requires explicit confirmation. Zero stock, excluded assortment and fully reserved availability follow existing guards.
- Existing Stage 3C CAS token, CSRF, request keys and pending-request recovery remain untouched. Opening an editor/action from the search detail closes that detail first, avoiding stacked dialogs.
- Existing autocomplete keyboard selection, 300 ms debounce, normal/smart interpretation and server-ranked smart explanations. Enter/Find uses the existing query state, without an extra reload for an already-current query. Text survives filter/mode changes. Clear filters preserves the query.
- Existing server pagination: 50 results, offset/total from the server, no client sorting or page-local filtering. Empty query retains the existing browse behavior. Stale responses are rejected by the existing loader/query guard. Normal search no longer refetches just because the independent smart readiness request finishes.

`PartsSearchControls` supplies the search-only layout, `partsSearchQuery` encodes the two existing API contracts, and `SearchPartPhoto` lazily reads the existing part-photo endpoint near visible rows. It uses an actual returned photo URL or a neutral package placeholder; broken photos fall back to the placeholder. No stock image guesses. The API has no batch photo endpoint, so these are individual, viewport-bounded reads.

## API limits

| Filter | Ordinary `/parts` | `/smart-search/parts` |
| --- | --- | --- |
| Name/OEM/article | Existing substring behavior | Existing interpreter/ranking |
| Vehicle, manufacturer, model | Supported | Supported |
| In stock | Positive enabled quantity | Positive enabled free quantity |
| Physical condition | Supported | Unsupported; disabled with explanation |
| Own-price presence | Unsupported; disabled | Unsupported; disabled |
| User sorting | Unsupported; not offered | Existing ranking preserved |

The ordinary search stock checkbox now exposes the existing API's `in_stock=false` option (as smart search already did), allowing zero/excluded entries without inventing a “sold” status. Condition selection is retained while switching modes but explicitly not applied in smart mode. Unsupported filters are never sent or simulated on the current page. Changing brand clears model/donor; changing model clears donor; choosing a donor aligns brand/model. No backend extension was made.

## Verification

Local production preview at 5203, local API at 8030, existing dedicated synthetic `warehouse_ui3_test` fixture. All search/stock data assertions use the actual local API; no real Volvo B or staging validation is claimed. No parser/import/publish/receipt/sale/price mutation ran. A read-only worker's price PATCH was intentionally rejected with 403; a foreign workspace part returned 404.

Commands from `warehouse/frontend`:

```
npm run build
node --test tests/*unit.mjs
WAREHOUSE_E2E=1 node tests/ui4-browser.mjs
WAREHOUSE_E2E=1 node tests/ui4-states-browser.mjs
WAREHOUSE_E2E=1 node tests/ui3-browser.mjs
```

Scripts require `/tmp/ui3-fixture.json` and local synthetic auth caches, created by the guarded UI-3 seeder (see UI-3 docs). They do not accept staging URLs. Auth caches are not committed. Before capture: `tests/ui4-before.mjs`, run before changes against the same fixture and `/search` alias. Final captures use canonical `/`; the old alias's pre-existing generic breadcrumb fallback is outside this redesign and was not changed.

Read-only browser QA covers 1440/1280/1000/900/768/390/375: blank search, hundreds of results, name/OEM/article, Enter without duplicate request, server pagination, donor filters, reset, mode switches, stock toggle/zero quantity, zero/absent own price, USD, long names, market guidance, opening the actual price editor/sale/context menu, mobile filters, overflow and JS errors. It compares complete inventory snapshots before/after.

The separate state harness injects only delayed/error/photo responses to test loading, stale-result rejection, error text/draft preservation, readiness fail-closed, photo rendering/failure and single-dialog keyboard navigation. It does not claim these injections are catalogue data or real photo uploads. UI-3 browser regression also verifies the shared row defaults, inventory filters/grouping, donor workflow and UX-1 statistics.

Results and screenshots are stored alongside this document. The existing Vite >500 kB bundle warning remains; no unrelated dependency/chunking refactor was introduced. Automated Chromium mobile viewports do not substitute for physical iPhone Safari acceptance.

## Screenshots

- [Desktop before](screenshots/search-before-1440.png)
- [iPhone before](screenshots/search-before-390.png)
- [Desktop after / ordinary results](screenshots/search-after-1440.png)
- [iPhone after](screenshots/search-after-390.png)
- [Market and own price](screenshots/search-price-1440.png)
- [Smart search](screenshots/search-smart-1440.png)
- [Mobile filters](screenshots/search-filters-390.png)

Final results: **build PASS; 428 frontend unit tests PASS; UI-4 browser QA PASS at all seven widths; UI-3/UX-1 browser regression PASS at all seven widths; states/permissions harness PASS**. Synthetic B-level prices remained “Схожі ціни”, never an A recommendation. Timeout retry preserved the search text and recovered without mutation. The final suggestion button explicitly has `type="button"` to avoid accidentally submitting the new search form; both keyboard and pointer selection were checked.
