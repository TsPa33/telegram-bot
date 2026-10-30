# UI-3 — Inventory interface

Frontend-only redesign of `/inventory`, based on UI-1 tokens and UX-1 hierarchy. No backend, migrations, catalogue, permissions or stock algorithms changed. No push or deployment.

## Presentation

Compact grouped desktop rows show the part, donor, actual quantity/reserves, recommended prices and own price together. Categories/subcategories collapse; each subgroup renders 50 rows initially with “Ще 50 деталей”. Mobile/tablet uses cards and collapsible filters. Unknown photos use a placeholder; long names wrap to two lines with full name available in the detail dialog. No provider branding or currency conversion is introduced.

Search, donor, category and condition reuse the existing API. Since that API has no own-price/subcategory filter, inventory reads all pages of the server-filtered result before applying those filters. This avoids silently missing rows after the first page. Large workspaces therefore still incur a complete result download; rendering is incremental, not server-side virtualization. Default scope remains active positive stock; “Усі неархівні” includes zero quantities and excluded assortment. Archive remains a separate existing screen. Zero quantity is not labelled as sold.

The shared vehicle lookup avoids duplicate reads and per-row donor requests. Quick search and the UX-1 donor parts view keep their existing workflows. Sidebar/navigation, design tokens and authorization are unchanged.

## Preserved operations

Existing create/edit, notes, inspection, history, reserve/release, receipt/correction, transfer, write-off, sale and archive controllers remain in use. Inventory detail closes before opening another editor. No implicit receipt or sale is introduced.

The existing stock bulk form is shared with advanced inventory: transfer/archive, permission-gated, maximum 100 parts. Owner bulk pricing keeps the existing 1000-part limit, preview, explicit confirmation, CAS/CSRF/replay and session recovery. “За фільтром” uses the complete filtered active IDs; “Усі” retains the existing server selection scope. Manual price editing reuses Stage 3C. Original UAH/USD amounts are preserved.

## Local verification

- `npm run build`
- `node --test tests/*unit.mjs`
- `WAREHOUSE_E2E=1 node tests/ui3-browser.mjs`
- `WAREHOUSE_E2E=1 node tests/ui3-write-browser.mjs`

Browser scripts require the dedicated local synthetic fixture `/tmp/ui3-fixture.json`, API 8030 and production preview 5203. `tests/seed-ui3.py` refuses to overwrite an existing fixture database and only accepts loopback `warehouse_ui3_test`. It copies synthetic global reference data in a read-only source transaction, then creates dedicated synthetic accounts/donors. Never point these scripts at staging or production. Auth caches remain outside the repository.

Read-only QA covers 1440/1280/1000/900/768/390/375px, more than 300 stock positions, complete-result filtering, 50-row expansion, category collapse, zero/absent own prices, USD, long names, history, donor mode and UX-1 statistics. Server permission checks use a read-only worker and a foreign workspace. Write QA uses only newly created/specially seeded local synthetic parts: create, receipt, edit, note, inspection, price conflict/draft recovery, sale, transfer, bulk price preview/confirmation/lost-response reload and archive/history retention. It verifies untouched reference parts remain identical.

See `browser-results.json`, `write-results.json` and screenshots. Before screenshots use the earlier separate synthetic UI-2 fixture, so counts are not a before/after data comparison. No real Volvo B or staging data was tested.

Results: production frontend build PASS; all 424 frontend unit tests PASS. Synthetic browser write workflows PASS, including exactly one audit entry per bulk-price target after a lost response and reload. All operations were local; no staging acceptance is claimed.

## Screenshots

- [Before desktop](screenshots/inventory-before-1440.png)
- [Before iPhone](screenshots/inventory-before-390.png)
- [After desktop / grouped list](screenshots/inventory-after-1440.png)
- [After iPhone](screenshots/inventory-after-390.png)
- [Recommended and own price](screenshots/inventory-price-1440.png)
- [Long name on iPhone](screenshots/inventory-long-name-375.png)
- [Bulk preview before confirmation](screenshots/inventory-bulk-preview.png)

The existing build warning about a bundle over 500 kB remains; no new dependency or chunking refactor was added. Screenshot/photo data is demonstrative. Inventory filters intentionally live in component state as before; they are not a new persisted preference system.

Final read-only browser QA: PASS at all seven widths (1440, 1280, 1000, 900, 768, 390, 375), no JavaScript errors, no domain writes, unchanged inventory snapshots. Read-only worker permissions and foreign workspace isolation PASS against the local backend. `WAREHOUSE_E2E=1 node tests/ui3-screenshots.mjs` captures the final compact layout with mobile filters initially collapsed.
