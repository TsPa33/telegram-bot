# Stage 2D — one-click safe dismantling plans

Base: `8ff26bc30a4cd82d2d27d3e216b5ae64c8bb47e0`. Changes are local and Warehouse-only. No push, Railway deployment, staging write, operational canonical publication, production action or main-bot startup was performed.

## Why the old flow blocked

`save()` required an entirely resolved preview: a single `review` caused HTTP 409. The UI independently disabled save whenever `counts.review > 0`. Consequently the reported staging result (336 candidates, 196 new, 140 review) could not create any useful plan without resolving every conflict. Those reported staging counts are not treated as a local measurement of real Volvo B.

The strict preview/save API remains compatible for existing clients. A new atomic command powers the ordinary workflow:

```text
POST /api/v1/vehicles/{id}/dismantling-v3/quick
```

Example body (values are supplied internally by the UI):

```json
{
  "facts": [],
  "etag": "<current plan-state hash>",
  "request_key": "<unique UUID>",
  "confirm": true
}
```

Optional `facts`, `selected`, `reset_trial` use the existing configuration resolver. Manual `resolutions` additionally require a completed preview `token`; main quick creation requires no token copy/paste or preliminary preview. Clicking the main button is the explicit confirmation. Response counts include `created`, `reused`, `pending`, `candidates`, `received: 0`, and revision.

## Partial-save policy

Quick Create uses the existing candidate generator and legacy matcher. It does **not** simply save everything formerly tagged `new`, nor ignore `review`.

1. Build the current candidate set under the existing catalogue advisory transaction lock and vehicle row lock.
2. Independently inspect a graph of overlapping generic/refined positions and shared possible legacy rows. An uncertain component is deferred, including a safe-looking `new` neighbor of an unresolved candidate. The graph traversal uses sets/indexes rather than enumerating all component pairs.
3. New unambiguous positions are created. Proven unique legacy/exact matches reuse the old ID. Within an overlap group a proven existing identity may be reused, but no competing new row is created. Several possible legacy targets or competing claims to one row remain pending.
4. Explicitly reviewed distinct physical identities can coexist. Saved explicit skips remain skips; accepted link/new identity and mapping reasons survive automatic refresh. Automatic generation never manufactures manual approval reasons.
5. A new candidate contrary to known configuration evidence is deferred for clarification. Already saved rows remain in place, including excluded, dismantled, received, sold and potentially incompatible historical rows. Neither unknown equipment nor a deferred candidate means physical absence.
6. Save only safe rows, vehicle plan metadata, audit additions and replay result in **one PostgreSQL transaction**. Any failure rolls back all of them. No category receipt, Part creation or price assignment is called.

Pending rows are stored in existing `Vehicle.dismantling_v3.pending_review`, with name, installation information, uncertainty reason, possible matches and what needs clarification. They are not `DismantlingItem`, user exclusions, absence decisions or hidden stock. They survive fresh requests/reloads. No migration or new ledger is needed.

A manual choice in a still-unsafe group is retained as a **draft**, not falsely applied. `review_drafts` preserves the actual user-entered action/reason. It is restored in the optional review UI; ordinary refresh does not silently apply the draft. The user can recheck it against current evidence or explicitly start a fresh review. Applied choices retain their existing row/skip history.

Unknown installation stays unknown. Preview quantity remains unverified/null; the existing plan row quantity default is only a draft workflow value. A separate receipt still requires a user-selected quantity and explicit confirmation.

## Retry, concurrency and security

- Existing session authorization, CSRF, `dismantling.manage`, server-derived actor/workspace and ownership checks apply. Inventory creation/quantity rights remain required only for an explicit receipt.
- `etag` rejects changes to the vehicle, plan or stock since the user read it. Vehicle row locking serializes competing commands. The existing database unique placement index remains a final fence.
- Replay lookup precedes stale-state checks: a committed command with the same key/payload returns its original result without applying again. A changed payload, actor or vehicle cannot reuse another command's key. Two distinct concurrent commands from one state produce one success and one controlled 409.
- The client stores uncertain command intent in sessionStorage, scoped to actor, workspace and vehicle. Reload does not submit automatically. “Відновити формування” explicitly repeats the **same payload and key**. Corrupt, oversized or foreign-scope intents are rejected locally; server validation and authorization remain authoritative.
- A known 4xx rejection clears uncertain intent. A stale manual decision disables application until a new check; typed resolutions remain available. Network/5xx uncertainty retains the command for an explicit retry.
- Quick Create is a synchronous transactional command, not a memory-only background task. A server failure leaves either the complete transaction/replay result or no committed changes; repeating the key is safe. An unpublished, stale or empty reference produces a clear error, rather than claiming that 33 fallback positions are a complete dismantling.
- Global reference, v2 offers/prices and platform-owner publication are unchanged. No quick command publishes a snapshot or enqueues normalization. No startup command creates plans or stock.

## UX

New donor: **“Розібрати авто на запчастини”** → progress → saved safe list. No mandatory separate preview, checkbox or hundreds of review decisions.

Existing managed plan: **“Оновити список деталей”**. Optional “Уточнити двигун і комплектацію” uses the existing facts/VIN-ready model; no full VIN decoder is introduced. Updating recalculates applicability and only adds safe relevant new positions. Existing inspections, exclusions, dismantling and stock history remain authoritative.

The main list keeps search, category/subcategory/state filters, collapsible groups, mobile cards and bulk actions. Six indicators show total, unchecked, physically confirmed, excluded, dismantled and actual positive stock. “Ще N деталей потребують перевірки” is collapsed by default and does not disable ordinary work. Manual matching opens only on demand. “Додати на склад” still requires a separate explicit quantity confirmation.

Normal screens do not show tokens, replay keys, etags, raw provenance or internal stage names. Legacy/source tools remain secondary; their records and APIs are retained.

Screenshots (real local auth/API, production frontend, Chromium viewport emulation):

- [Phone before creation](screenshots/stage2d-new-390.png), [saved plan](screenshots/stage2d-ready-390.png), [cards](screenshots/stage2d-cards-390.png).
- [Desktop before creation](screenshots/stage2d-new-1440.png), [saved plan](screenshots/stage2d-ready-1440.png), [cards](screenshots/stage2d-cards-1440.png).

This is not a physical iPhone/Safari certification.

## Measurements and data boundaries

[Controlled synthetic 336-candidate PostgreSQL/API test](synthetic-336.json):

| Input / result | Count |
|---|---:|
| Potential candidates | 336 |
| Planner tagged new | 196 |
| Planner tagged review | 140 |
| Actually created safe rows | **196** |
| Durable pending | **140** |
| Created on repeat | **0** |
| Receipts / stock created | **0** |

The 140 pending candidates form 70 generic/refined ambiguity groups. An additional adversarial test changes one uncertain neighbor's label to `new`; the independent partial policy still defers the entire group. Therefore 196/140 are **test data**, not application constants or guaranteed staging results. Real candidates can yield fewer safe additions if more conflicts are discovered.

[Actual local generator/browser fixture](browser-results.json) uses the real canonical candidate pipeline with a clearly synthetic reference snapshot (216 constructive functions and an explicit refined mirror source). It produces **228 candidates → 226 created / 2 pending** for a fresh XC60 2018. Optional explicit review then creates one precise row while skipping the redundant broad candidate: 227 rows, no stock. Diesel refresh reuses existing rows without resetting dismantling. The reference rows are fixture construction only; the fixture does not call canonical publish/queue APIs.

Historical fixture, independently checked in PostgreSQL and browser: 33 original plan IDs, 30 receipt histories, one sold part and 29 positive stocks. Tests preserve every old ID, status/exclusion/receipt link, Part rows including cost/selling price/archive state, and every pre-existing Operation. New audits record only explicit plan commands. No existing staging XC60 was read or changed.

Real Volvo B is unavailable locally and **was not tested**. No local count is represented as a result of its 10,222 offers. Existing catalogue counts and real donor history must be checked separately during a later authorized staging acceptance.

## Reproduce locally

Tests and fixture seed require dedicated disposable loopback `warehouse*_test` databases and erase their fixtures. Never point them at staging.

```sh
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage2d_suite_test \
  python -m pytest tests/test_stage2d.py -q

# Separate browser DB must already exist and be migrated to head.
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage2d_browser_test \
  python scripts/seed_stage2d_browser.py --confirm-disposable
```

Start a local API on 8018 with that browser DB, loopback insecure cookies only, and catalogue worker disabled. Serve `npm run build` assets on Vite preview 5188 with `WAREHOUSE_API_PROXY=http://127.0.0.1:8018`. The browser fixture account is synthetic and documented in the seed script; no Railway variable is touched.

```sh
cd warehouse/frontend
WAREHOUSE_E2E=1 node tests/stage2d-browser.mjs
node --test tests/*unit.mjs
```

The browser scenario requires a fresh fixture before rerun. It uses the real generator, authenticated API and production frontend; only lost-response/stale-HTTP faults are injected. It checks one command/no preview on initial creation, no duplicate double click, network loss/reload/same-key replay, nonblocking pending, explicit review, stale decision recheck, diesel refresh, old donor stock preservation and no horizontal overflow at 1440/390px. It never performs receipt or canonical publication.

## Next staging release

Requires separate authorization for a normal fast-forward push and API/Web deployment. This task does neither. Alembic head stays `84d2c6fa190b`; no Stage 2D migration, new Railway variable, catalogue re-import or normalization/publication is required.

Before release confirm the existing canonical snapshot/rules are usable. After deployment first use a dedicated test donor/workspace, inspect actual candidate/created/pending counts and verify repeated commands create no duplicates. Inspect the existing donor read-only; do not run Quick Update on a real donor without its explicit user action. Do not infer the real B result from the synthetic 336 case. No backfill or automatic receipt is part of deployment.

## Completed checks

- Full backend: **494 passed, 1 skipped**, 521.14s. The skip is the unrelated opt-in 100k smart-search benchmark. Includes all 11 new Stage 2D cases, existing strict workflow, real-A legacy regressions, finance/authorization and migration checks.
- Frontend unit tests: **354 passed**, including actor/workspace/vehicle-scoped uncertain intent restoration, exact request-key preservation and rejected malformed storage. Production build passed.
- Native browser: **1440px and 390px passed**, real local server/generator and production assets. Includes lost-response/double-click/reload replay, nonblocking pending, manual stale-409 recovery, explicit reviewed refinement, diesel refresh and unchanged historical stock. No canonical/receipt POST occurs in the browser workflow.
- Alembic: one head `84d2c6fa190b`; metadata/schema check reports no new upgrade operations. No migrations added.
- `git diff --check` passed. All changed/new files are under `warehouse/`.

No staging acceptance or real B test is claimed by these checks. The final local commit SHA is reported by `git rev-parse HEAD`; no push is authorized by this work.
