# Stage 2E — bulk selection and guided stock receipt

Local implementation based on `61c6652d26b8a80001fd6e6aa23cd1f7a1636256`.
No push, deployment, staging mutation, canonical publish or production operation was performed.

## User workflow

Select all available rows, a complete category/subcategory, or all filtered matches. Selection uses the authorized server selection endpoint, paginated at 1,000 IDs, rather than the first 60 rendered cards. Category checkboxes indicate partial selection. Protected, received and archived rows cannot enter disallowed actions.

The persistent action panel reports eligible counts and blocking reasons. Confirm physical presence, then actual dismantling. “Додати на склад” opens a separate guided screen showing selected/present/dismantled/received/blocked totals. Only initially eligible rows can be received. Review each quantity, optional condition, storage location and selling price, then explicitly confirm. Quantity defaults to 1; reference Aleto prices are never copied. Receipts use the existing Part/Operation ledger; the resulting stock is accessible through the ordinary inventory screen. Additional field permissions remain enforced server-side.

On mobile, the selected list scrolls within a bounded workspace; the action panel occupies separate space rather than covering cards. Categories collapse, and receipt fields are progressively disclosed.

## Transaction and recovery contract

The server accepts at most 1,000 unique IDs per command. The browser sends reversible actions in portions of at most 1,000 and receipts in portions of 100. Each command commits its complete eligible subset atomically; blocked rows are returned unchanged. **The whole multi-command selection is not one transaction.** Successful earlier portions remain committed if a later portion fails. Progress and this limitation are shown before receipt.

Each portion has a durable server replay key and a preview/state token. Vehicle locking serializes writes. Changed state stops subsequent portions. A sessionStorage checkpoint, scoped by actor/workspace/vehicle, preserves the exact pending payload/key across reload. Nothing resumes automatically: the user explicitly continues. A lost HTTP response replays the same key before advancing, preventing duplicate receipt. Validation failures stop processing; unknown network/server outcomes retain the pending key for safe retry. This checkpoint is browser-session recovery, not a server background queue. Closing the tab/session can discard the client checkpoint; the server ledger and replay records remain authoritative.

## Presence counters

An actual synthetic Quick Create regression creates 196 unchecked positions despite confirmed fitment evidence. Only an explicit manual bulk decision changes 194 to present; reload and repeated generation preserve 194 present / 2 unchecked, without stock. The UI distinguishes user confirmation, historical workflow evidence and fitment. No historical decision is reset. The cause of the real staging donor’s historical 194/2 count was not inspected in this local task.

## Verification

- Full PostgreSQL backend suite: **502 passed, 1 skipped**, 543.95 s. The skip is the unrelated opt-in 100k search benchmark. Eight new Stage 2E tests cover complete/paged selections, presence counters, mixed receipts and quantities, rollback after a flushed first receipt, replay/concurrency, RBAC, CSRF, workspace isolation and historical ledger preservation.
- Frontend unit suite: **363 passed** (nine new bulk tests).
- TypeScript / Vite production build: **PASS**.
- Native Chromium against the local API and PostgreSQL: **PASS at 1440×900 and 390×900**. Each width exercises 1,105 selected rows (1,000 + 105 commands), 700-row subcategory, 11 filtered rows, category tri-state, readable cards beside the action panel, mixed receipt of 2/3 selected items with quantities 2 and 4, ordinary inventory detail quantities, duplicate receipt returning zero updates, and explicit 194/2 counters. Desktop also loses the receipt response after commit, reloads and resumes the identical request safely.
- Synthetic historical donors retain 33 plan rows, 30 receipts and 29 positive stock rows; original history and prices remain unchanged.
- Alembic head remains **84d2c6fa190b**; no new migration or startup job/backfill.

All datasets are disposable local synthetic fixtures, not real Volvo B. No claim is made about staging counts or real-data performance.

## Repeat checks

Backend (dedicated disposable PostgreSQL only; the suite erases its test DB):

```sh
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage2e_test python -m pytest -q
python -m alembic heads
```

Frontend:

```sh
cd warehouse/frontend
node --test tests/*unit.mjs
npm run build
```

Browser: migrate a separate `warehouse_stage2e_browser_test` local DB; seed it with `backend/scripts/seed_stage2e_browser.py --confirm-disposable` using WAREHOUSE_TEST_DATABASE_URL. Run API against that DB with COOKIE_SECURE=false and CATALOGUE_WORKER_ENABLED=false; serve the production frontend at 127.0.0.1:5189 with API proxy to 8019. Then run `WAREHOUSE_E2E=1 node tests/stage2e-browser.mjs`. Seed again before every complete browser run. This creates only local disposable test data, including deliberate receipts.

## Evidence and release

[Browser results](browser-results.json)

| Screen | Desktop | iPhone |
|---|---|---|
| Selection | [1440px](stage2e-selection-1440.png) | [390px](stage2e-selection-390.png) |
| Guided receipt | [1440px](stage2e-receipt-1440.png) | [390px](stage2e-receipt-390.png) |
| Ordinary inventory | [1440px](stage2e-inventory-1440.png) | [390px](stage2e-inventory-390.png) |

Ready for a separately authorized staging release of API and Web. No migration, canonical publish, re-import, backfill or automatic receipt is required. Verify the deployed UI and read-only historical counts first; any writable smoke test must use an authorized dedicated test donor/workspace. Do not use an existing donor with stock history.
