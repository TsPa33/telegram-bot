# #502 — local acceptance and staged review handoff

12 November 2026, Europe/Kyiv. **Local functional acceptance passed; live staging acceptance pending.** No push, Draft PR publication or deployment is performed after the owner's clarification. PR499/501 are preserved through the exact a0d00c2 baseline; no merge into main/shared staging.

## Changes and evidence

| Package | Minimal change | Evidence / DONE |
|---|---|---|
| A: VIN → free plan | Move existing generator outside collapsed modification controls. Preserve uncertain provider year as evidence; require manual year correction instead of guessing. Bounded vin_details diagnostics/consistency schema, no new table. | 29 PostgreSQL backend tests; real browser free plans for PEUGEOT/Renault/Volkswagen, 227 potential positions each, zero Parts; refresh preserves plan. VIN form autofill/edit/create uses an explicitly labelled decoder fixture, real auth/API/PG. |
| B: assembly references | Reference selection opens current parent inspector/split controls; selecting a suggestion does not assert presence/create SKU. Existing physical transaction retained. | 55 physical backend regressions (also included in C81); authenticated browser qty1/qty6, preview503, damaged component selection, explicit two-component split, root remains qty1, original IDs/qty6 unchanged. |
| C: one checkout | Inventory/search/card use OrderComposer. Assembly composition metadata survives basket and line edits. Optional search below basket. Explicit draft/reserve/sell, one server transaction using existing orders.command/action/stock and request ledger. Legacy stock API retained. Fail-closed route registry and permissions. | 81 order/assembly tests; 11 new checkout tests incl replay/concurrency/CSRF/workspace (5 overlap C81); team/security suite. Browser 1/2-line multicurrency orders, edit price, confirm, reload, exact remaining stock. |
| D: shared UX | Reuse corporate category/list/inspector geometry for sales; compact existing PartCard actions; Settings General/Payments display-only, desktop explicit/keyboard/hover compact navigation, mobile focus preserved. Provider diagnostics admin-only; existing provenance unchanged. | Frontend build and 258 tests; authenticated browsers day/night1440/1920/390, no page horizontal overflow, keyboard tabs, theme persistence, mobile Escape/focus. Screenshots animations disabled to capture settled theme colors. |

**Final combined backend run: 139 PASS on the dedicated localhost PostgreSQL. Final frontend prebuild: 258 PASS; production build PASS.** Evidence is under [evidence](evidence). `before/` reproduces hidden free-plan control and legacy direct-sale modal with baseline a0d00c2's local production bundle; no sale is performed there. `shared/`, `final-assembly/`, `final-checkout/` are local test records, **not staging**. Legacy first-run logs are retained; final logs supersede them. Exact source owner16 screenshots are unavailable and are not claimed attached or matched pixel-for-pixel.

## Contracts, models, safety

- Existing Vehicle, DismantlingItem, Part, AssemblyMembership, Operation, Order, OrderLine, OrderReservation and request/event history remain the authoritative models. No alternate ledger, queue or availability system.
- Catalog216 types /227 placements is a generic potential plan, not a factory BOM or independently saleable physical stock. Source coverage remains explicit; unknown applicability is not silently incompatible.
- Existing stock_guard remains active for order/reserve/direct legacy sale/correction/receipt/bulk/virtual paths. Parent+child conflict, reservation, archived/absent stock, replay, concurrency and atomic failure are covered by existing physical/order tests.
- No migration/backfill. Packaged head remains `08b72c9d4e16`. Actual staging revision is not read. VIN JSON accepts bounded evidence fields; arbitrary diagnostic keys remain rejected.
- ORM index name `vehicle_directory_variants.account_id` is aligned to the already-created `ix_vehicle_directory_account_id`. This removes an Alembic metadata-only rename proposal; no database index operation is performed.
- Two historical team tests assumed downgrade through a forward-only VIN migration. Tests now assert deliberate refusal, preserved current-head snapshots, cookies/reserves/orders/request replay and repeated current-head upgrade. They no longer claim to simulate the obsolete historical downgrade/DDL retry. No migration guard is weakened.
- Existing analytics exclude null unit_cost from calculated margin. Separated components do not receive invented cost. UX warns to reconcile residual assembly/component costs before profit reporting. A future approved cost-allocation policy must reconcile total cost and record author/reason; this package does not distribute cost or alter finance.
- A qty6 lot remains explicitly BLOCKED for split until a controlled, verified unit-extraction transaction can preserve quantity, cost, reservations and order identities. Do not manually decrement/re-receive or claim six units are one physical assembly.
- No source MySQL, paid API, production/staging write, worker/variable change, catalogue publish, payment provider or export feature.

## Review/staging acceptance — owner-controlled, not executed

Review A → B → C → D as stacked Draft PRs; base each on preceding package, not main. Restore exact commits from the transfer bundle; patch alternatives are content-only. Review migration absence and API/frontend compatibility. New UI requires readiness feature `atomic_checkout` before checkout submission; legacy clients retain existing routes/version6.

Before any deployment, authorized operator must confirm warehouse-staging service branch bindings and isolation, deployed Web/API SHA and database head. No production or worker changes. Approve the four reviewed packages, then deploy only the agreed candidate via existing workflow; do not run manual migrations.

1. Read-only health, startup/runtime logs, deployed assets/SHA and head. Record actual URL and authenticated role. A local PASS is insufficient.
2. Use a separately authorized isolated QA workspace/donor; capture initial per-Part quantity/reserved/archived flags and history counts. Never reuse owner working stock.
3. Create ≥3 makes (VIN/manual, exact/unknown modification). Real free VIN provider responses must be distinguished from fixture tests. Correct uncertain year explicitly. Generate base plan with no tokens; verify applicability/coverage, save/reopen, zero stock before explicit receipt.
4. Confirm actual presence/dismantling and guided receipt for selected QA positions only. Inspect tree/reference vs physical SKU. Qty1 bumper/door split: select physically separated components/condition, confirm, retry/reload; parent incomplete, new unique children, no duplicate receipts. Qty6 shows blocker and no mutation.
5. Checkout one/two lines from inventory/search/root/remainder/component, optional '+', edit price/currency, select buyer/action, explicit sale. Confirm exact sums per currency, one deduction, retained audit; draft no deduction, reserve no sale, stale composition requires renewed confirmation. Check order/legacy concurrent requests only on isolated QA stock; one winner.
6. RBAC/CSRF/workspace negatives; reserved/sold/archived restrictions, parent+child conflict, no fabricated margin. Verify child sale does not consume root.
7. Day/night1440/1920/390, keyboard/desktop toggle/mobile focus, photo/OEM/location/history card; no JS errors/overflow, no technical source noise.
8. Read-only compare post-state with expected deltas and operations, record evidence, leave working data untouched. Owner approval is required before any cleanup or real-data operation.

Rollback is application-only per reviewed package; preserve nullable VIN JSON and all recorded ledger/order history. Never downgrade forward-only evidence, reset stock or delete confirmed components to roll back UI.

## Remaining gates

- Live staging DOM/artifacts/SQL aggregates and real free-provider VIN responses are UNVERIFIED: CONNECT403/no authorized browser/Railway channel in this execution environment. No proxies or repeated failed access attempts.
- Actual Peugeot donor34 VIN/record was not accessible; no unsupported correction of its 1987 year is claimed.
- Qty6 extraction and approved cost allocation remain explicit limitations, as permitted in #502; no fake implementation.
- Bundle-size advisory (~780kB main JS) and Starlette/httpx deprecation warning do not fail current checks.
- Publish the prepared separate Draft PRs through the main ChatGPT GitHub connection, then perform the separately approved staging acceptance. **Issue502 is not declared staging-complete.**
