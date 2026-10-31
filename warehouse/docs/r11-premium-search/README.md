# CarPot Warehouse R11 — Search screen UX

## Scope
Only Warehouse frontend code. Approved graphite/emerald design retained. Existing inventory, smart search, pricing, sales, permissions and photo endpoints are reused, not rewritten.

## Delivered
- Premium search header, controls, input, results table.
- Real quick category tiles from the existing `/categories` endpoint. All root categories are available via expanding "Ще"; initial 7 tiles are a convenience subset. No invented counts.
- Clicking a tile triggers server-side `category_id` filtering on the **ordinary** `/parts` API and resets pagination. The smart search API does not support this filter: tile selection explicitly switches to ordinary search. Switching to smart search clears the category.
- Unknown Russian category terms remain unchanged; a small safe dictionary translates only known labels **in the UI**, not in PostgreSQL.
- Real OEM, article, condition, donor, market pricing, stock, own selling price and existing actions.
- Optional desktop part preview to the right; narrow screens show an explicit user-opened, dismissible preview above results.
- Existing part card, sale actions, inventory events, price editor, keyboard autocomplete, stock state and permissions unchanged.
- Nonfunctional disabled own-price filter omitted from quick search. Sorting and saved searches in the design concept are **not implemented** (no existing supported backend contracts).
- No backend schema or migrations; no data writes from appearance changes.

## Verification
Run `cd warehouse/frontend && npm ci && npm run build && node --test tests/*-unit.mjs`.
New tests assert category_id is sent only to the ordinary server query and not to the smart endpoint.

## Staging review checklist
- Desktop 1440+ width: chips, real result rows, side preview, sale and card actions; no horizontal overflow.
- 1280/1000/900/768/390/375: responsive category strip, result cards, "Швидкий перегляд" scroll and close.
- Search by name, OEM, article; stock-only/zero, brand/model/vehicle, physical condition, category and clear.
- Pagination count after category change, keyboard autocomplete Enter still opens the original card.
- Smart mode stays available without unsupported category/condition query params.
- Role without catalogue access gets search without forbidden enrichment; no leaks.
- No invented inventory quantities, prices or per-category counts.
