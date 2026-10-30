# R1 — Part card and action menu

## Pre-implementation audit

Base `d0cb4c06da29e68f49da02c8046a52d38fc054c7`. Stock/search share SalesWorkspace detail and PartActions; advanced Inventory and VirtualDismantling call exported PartDetail. CompactParts opens the VirtualDismantling modal. PowertrainEditor currently edits donor engine/transmission through the existing powertrain PATCH. Legacy PartDetail owns photos and optional advanced StockForm. Existing whole-form Part PUT resets defaults, so it is unsuitable for quick single-field edits.

| Characteristic | DB/API before R1 | Existing edit | R1 |
| --- | --- | --- | --- |
| OEM | Part.oem_number | Full Part PUT | Narrow compare-and-set PATCH |
| Internal article | Part.article_number | Full Part PUT | Preserve, secondary display |
| Color / paint code | Absent | None | Nullable color_name / paint_code; additive migration |
| Engine type | Vehicle.fuel_type | Vehicle full update | Extend existing powertrain PATCH to this existing field |
| Engine code/description | Vehicle.engine | PowertrainEditor/PATCH | Reuse, inline within card |
| Transmission type/code/description | Vehicle.transmission | PowertrainEditor/PATCH | One manual text field; no duplicate dictionary/fitment field |
| Condition | Part.condition | Inspection PATCH | Preserve |
| Location | Part.location / physical_location_kind | Stock transfer | Display; preserve explicit existing operation |
| Quantity/reserves | Part.quantity/reserved_quantity | Explicit stock operations | Display only by default; no implicit writes |
| Price | Part.selling_price/currency | Stage 3C CAS editor | Reuse, keep recommendations separate |
| Notes/photos | Existing fields/endpoints | Notes CAS/photo upload | Preserve in shared card/secondary tools |

All work is local to /warehouse. No push, staging writes/migrations, deployment or production operations.

## Implementation

`PartCard` is shared by the exported `PartDetail`: stock, ordinary/smart search, advanced inventory and VirtualDismantling/CompactParts now use the same core. The existing outer Modal provides the part name. Core content shows donor/year/number, stock state, actual book quantity/reserves and an explicit warning for assumed quantity; OEM, color, paint code, condition, presence check and location follow. Unknown attributes say “Не вказано”.

`PowertrainEditor` has an optional inline mode. It edits the existing donor `fuel_type` / `engine` / `transmission` fields, not part-specific fitment. Engine type is separate from engine code/description; transmission remains the existing single manual type/code/description string. No new engine/transmission dictionary or duplicate columns. Donor identification changes retain the existing `ktype` invalidation policy; no donor plan, Part, receipt or catalogue candidate is created or updated automatically.

Stage 3C `PriceSummary`, `SellerPriceEditor` and the existing guidance hook are reused. A recommendations remain distinct from B/C similar offers, with original currencies and no provider branding/conversion. Changing metadata invalidates read-only guidance caches, not selling prices. In the isolated fixture, editing donor powertrain can legitimately change an A match to C under the existing algorithm; the card is checked against the actual guidance API, not forced to show a recommendation.

Internal article, cost and legacy technical fields are secondary. Existing values, photo viewing/upload and explicit legacy stock tools remain available under a collapsed section. VirtualDismantling retains its original explicit condition, quantity-correction and shelf-transfer forms under a separate collapsed section; its duplicate own-price editor was removed because the shared card now supplies the same Stage 3C editor. No stock operation runs merely by opening/closing a card.

Stock/search use `PartActionMenu`: consistent icon/left-aligned rows, permission-filtered commands, separators and an expandable stock group. Quick search retains its separate primary Sale button, avoiding a duplicate Sale command in that menu; compact stock includes Sale within the menu. Existing controllers handle sale/price/notes/inspection/edit/history/archive. Transitioning from a card to another operation closes the card first. ArrowUp/Down, Home/End, ArrowRight/Left, Escape, touch scrolling and viewport bounds are checked. Popup height uses available room on the selected side of its trigger.

The common Modal now restores its invoking focus after unmount, while avoiding stealing focus from a newly opened dialog. RecordForm has a synchronous submit guard for the reused powertrain form (and other existing callers); price/stock business handlers are unchanged. Read-only users do not receive OEM/color/edit/stock actions they lack permission for.

## Additive backend contract

New nullable Part columns:

- `color_name`: varchar(80), default NULL.
- `paint_code`: varchar(40), default NULL.

Migration: `b7e14d90c2f6_part_color.py`, down_revision `a6d94c72e310`. Single head: `b7e14d90c2f6`. Upgrade is two ADD COLUMN statements, without UPDATE, backfill, stock/price changes or new business tables. Downgrade refuses if any current or archived part has a non-null new characteristic, preventing unattended loss of captured data. No staging migration was run.

New `PATCH /api/v1/parts/{id}/characteristics` uses the existing secure router, CSRF, tenant ownership, active-row lock and `inventory.edit` permission. Body example:

```json
{"values":{"color_name":"Білий","paint_code":"614"},"expected":{"color_name":null,"paint_code":null}}
```

Only `oem_number`, `color_name`, `paint_code` are accepted, with identical nonempty key sets in `values` and `expected`. Length/control-character validation is server-side; colors may be cleared to NULL, OEM to an empty string. It writes only those fields. A changed expected value returns 409 atomically. The same values already present return success without another audit entry: this is value-idempotent CAS, not a new request/replay table. If an intervening editor has changed values, a stale retry conflicts rather than overwriting them.

Existing Part POST/PUT accepts the optional fields. PUT **preserves them when omitted**, so old full-form clients do not reset newly captured colors. Existing response consumers use additive Row objects. The old full PUT's broader historical semantics were not rewritten; quick edits never use it. Existing audit `part_update` records append before/after snapshots only for an actual characteristic change; old audit/sale snapshots remain untouched.

Existing `/vehicles/{id}/powertrain` additionally accepts the already-present `fuel_type`, with its existing `vehicles.edit`, lock, audit and no-op semantics. Other callers may still send only engine/transmission. This endpoint retains its existing last-writer behavior, unlike the new field-level CAS characteristic endpoint. The existing frontend readiness allowlists and test expectations were updated for the new additive head, preserving acceptance of previous compatible heads.

## Verification

- Frontend production build PASS; full unit suite **442 PASS**.
- Backend targeted suite **37 PASS**: characteristics, Workshop stock/sale snapshots, vehicle UX, dismantling readiness and staging startup/migrations. Includes **8 R1 tests**, repeated after final validation changes.
- Populated local upgrade from `a6d94c72e310` to the new head preserves every original Part column and operation count; repeated upgrade is a no-op; old row new fields are NULL. There is no parallel head.
- Backend coverage: validation/forbidden field injection, CSRF, read-only permissions, foreign workspace 404, archived-part refusal, concurrent CAS, repeated-value no-op, old PUT field preservation, donor updates without stock changes, immutable existing stock/reserve/price/sale/audit data.
- R1 browser PASS at **1440/1280/900/768/390/375px**: menu bounds/keyboard/Escape/focus, shared card, inline editors, one modal, actual guidance level, no horizontal overflow or JS errors.
- Isolated write browser PASS: OEM conflict retains draft, double submit sends one request, color/paint persists after reload, lost response retries without duplicate audit, repeated menu edit reopens correctly, powertrain double-submit guard, only characteristic/powertrain PATCH requests. Every other Part field, all other parts, sales, catalogue and prior audit rows remain identical.
- State browser PASS: a delayed initial GET cannot overwrite a newly saved OEM; read-only card/menu/price/powertrain and the server permission remain protected.
- UI-3/UI-4/UI-5 browser regressions PASS at their seven widths. Existing menu assertions were updated to the new menuitem semantics; those page layouts/routes/financial logic were not redesigned.

Only local synthetic PostgreSQL databases were used: `warehouse_r1_test` for browser writes and `warehouse_r1_unit_test` for disposable pytest fixtures. Source UI-3 synthetic data remained unchanged. The R1 browser DB was initialized fresh using the guarded UI-3 seeder's synthetic catalogue reference data, not a real Warehouse copy. `tests/seed-r1.py` reproduces this for a fresh target and refuses an existing database. No real Volvo A/B or staging behavior is claimed. Before screenshots use the existing separate UI-3 fixture; after screenshots use the isolated R1 fixture, including explicitly edited donor data. Values/counts are not a before/after production data comparison.

API 8032 / production preview 5206 were used. The local fixture and synthetic auth cache live under `/tmp` and are not committed. Backend test fixtures only target a separate `_test` database; they must never be pointed at staging/production. Reproduce from backend with `WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_r1_unit_test /workspace/.venvs/warehouse/bin/python -m pytest tests/test_part_characteristics.py tests/test_workshop.py tests/test_vehicle_ux4.py tests/test_dismantling_readiness.py tests/test_staging.py -q`. The R1 synthetic seeder expects the existing synthetic Stage 3C reference DB described in UI-3 docs.

Frontend commands:

```
npm run build
node --test tests/*unit.mjs
WAREHOUSE_E2E=1 node tests/r1-browser.mjs
WAREHOUSE_E2E=1 node tests/r1-write-browser.mjs
WAREHOUSE_E2E=1 node tests/r1-states-browser.mjs
WAREHOUSE_E2E=1 node tests/ui3-browser.mjs
WAREHOUSE_E2E=1 node tests/ui4-browser.mjs
WAREHOUSE_E2E=1 node tests/ui5-browser.mjs
```

Write tests mutate only specially seeded metadata in the isolated R1 browser DB, never stock quantities, reserves or selling prices. Browser harnesses inject only a stale GET, a concurrent-edit error and a lost response; normal metadata/powertrain writes and permission checks use the real isolated API. No fake catalogue metrics are used. Physical iPhone Safari acceptance remains separate from Chromium viewport QA. The existing Vite >500 kB bundle warning and TestClient deprecation warning remain.

## Next controlled staging release

This change requires **both API and Web**, unlike UI-3/UI-4/UI-5. Before an authorized release, fetch/verify the branch and actual staging Alembic revision. The intended additive step is `a6d94c72e310 → b7e14d90c2f6`; verify any older actual revision's full upgrade chain rather than assuming it. The existing `python -m app.staging` startup applies Alembic before serving. Do not run manual migration/publish/backfill as part of this local task.

Coordinate API and Web deployment: the new frontend accepts old compatible heads, but old frontends use strict head allowlists and can temporarily fail closed after API upgrades until the new Web is online. Check API startup migration completion, `/health`, actual revision, both deployed SHAs, readiness and read-only card/menu behavior. Do not automatically downgrade or clear characteristic data. No catalogue import/publish, donor plan update, receipt, sale or real metadata write is required for release acceptance. Staging runtime/authorized-browser QA has not been performed here.

## Screenshots

- [Card before desktop](screenshots/card-before-1440.png) / [after desktop](screenshots/card-after-1440.png)
- [Card before iPhone](screenshots/card-before-390.png) / [after iPhone](screenshots/card-after-390.png)
- [Menu before desktop](screenshots/menu-before-1440.png) / [after desktop](screenshots/menu-after-1440.png)
- [Menu before iPhone](screenshots/menu-before-390.png) / [after iPhone](screenshots/menu-after-390.png)
- [Explicit synthetic edits](screenshots/card-edited-390.png)
