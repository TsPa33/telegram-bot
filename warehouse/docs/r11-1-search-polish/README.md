# CarPot Warehouse R11.1 — Search usability refinement

## Changes
1. Full "Продати" button with no clipped text. Reuses the original guarded sale action and does **not** write any sale without explicit form confirmation.
2. A result card can be selected by clicking its background or "Швидкий перегляд". The preview has previous/next arrows for current-page items and a counter. Existing "Open part" action remains available.
3. Photo upload reuses `POST /api/v1/parts/{id}/photos` with JPEG/PNG/WebP, 5 MiB validation, role `inventory.edit` and the existing authenticated image endpoint. Successful uploads refresh the selected photo and result thumbnail without reloading the page.
4. On the preview, safe existing `PartCharacteristicsEditor` (OEM with optimistic concurrency token) and `SellerPriceEditor` (idempotent price mutation and explicit currency) can be used. "Редагувати дані" opens the existing full editor. Inventory quantities are never changed from preview.
5. Search controls and category tiles use tighter spacing and a single horizontal row by default. "Ще" expands the full real category list.

## Persistent photo storage (staging only)
The existing warehouse API requires `WAREHOUSE_PHOTO_DIR` and a persistent volume, and currently disables uploads without them. On Railway `warehouse-staging` only, attach a dedicated persistent volume to the **API** service at `/data/photos`, set `WAREHOUSE_PHOTO_DIR=/data/photos`, and confirm API startup plus photo upload as the authorized user. Avoid adding a volume to the frontend or worker, because the existing authenticated API serves the files. Volumes incur storage charges. Do not change production.

The backend API process uses an unprivileged UID 1000. Railway mounts new volumes as root; the new `api-entrypoint.sh` only chowns the dedicated photo mount before dropping privileges with `gosu`. It rejects any unexpected `WAREHOUSE_PHOTO_DIR` path. The API remains nonroot; no database migration is required.

## Checks and acceptance
- `cd warehouse/frontend && npm ci && npm run build && node --test tests/*-unit.mjs`.
- `docker build -t warehouse-api -f warehouse/deploy/railway/backend.Dockerfile warehouse` from repository root.
- Docker smoke: attach disposable root-owned volume at `/data/photos`, set `WAREHOUSE_PHOTO_DIR`, assert the process runs with UID 1000 and writes a test file.
- Authenticated browser on 1440 / 1280 / 1000 / 900 / 768 / 390 / 375 px: no action clipped, arrows navigate correct part, filters and smart mode, photo after reload, OEM and price guards, unchanged permissions and original part dialog.
- Storage-disabled state must clearly indicate unavailability, not show a fake upload action.
- No changes to core CarPot, catalogue import, stock or financial calculations.
