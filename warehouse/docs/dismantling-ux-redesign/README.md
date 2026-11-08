# Vehicle dismantling — unified UX redesign

Frontend implementation completed locally on `integration/volvo-unified-catalogue`,
based on `fd48fcb3cd28cb8d151b54bda13f4454c97a56d8`.
Real authorized staging integration acceptance: **UNVERIFIED**. No deployment/push,
paid Plan.Parts call, production operation, migration or working-data modification.

## Root cause and structure

`UnifiedCatalogue` previously simultaneously rendered a Catalogue selection card,
the complete independent `PlanPartsDonorAnalysis` page and a separate basic-plan
card. Plan.Parts itself rendered its heading, start card, technical selection,
selection button and another modification action. The same vehicle therefore
had multiple visible starts and sources competing for the user's attention.

New single coordinator:

1. Preparation: saved vehicle facts, one exact modification selector. Source IDs
   remain distinct internally. Model generation is not inferred from year alone.
   Existing matches are read first; searching for new matches opens the existing
   explicit price confirmation, never an automatic paid request.
2. Plan: compact selected-modification summary and one list-choice field. A
   Catalogue option is offered only when both coverage and taxonomy are verified.
   Partial/unreviewed data get a short explanation and allowed alternatives.
   Basic-plan preparation remains free; external retrieval uses the unchanged
   recovery-first / tariff / confirmation / request-key / credit handlers.
3. Workspace: saved summary, four actual read-model counters, compact category
   tabs, search/filter/list and the existing part preview. Intro forms disappear;
   one existing DismantlingBoard handles the saved source. No second ledger.

`PlanPartsDonorAnalysis` now optionally exposes a render-flow interface over its
existing handlers. The same board, details dialog, payment confirmation and
translation behavior are reused. Legacy layout remains available for compatibility,
but is not mounted as another screen inside the new process.

## Presentation and interactions

- Vehicle context is compact only in parts/settings tabs; other vehicle tabs keep
  their normal layout. Global tabs are not duplicated. Photos, full vehicle facts,
  finance and editing remain in existing routes/dialogs. No photo/data deletion.
- Existing dark sidebar, Day/Night tokens, fonts, borders and radii retained.
  New CSS is scoped to `uf-*`/integrated board; no parallel global theme.
- Category tabs show actual populated categories, with readable active counts.
  Mobile tabs scroll within their own container; no page-level horizontal overflow.
- Bulk actions appear after selection and show the selected count. List pagination
  and selection still operate on the entire matching set, not the visible10 rows.
- Stock/receipt/state/article/OEM handlers, server guards and audit are unchanged.
  A stale own plan shows a review banner and disables its source-dependent writes.
  Existing Part editing/quantity permissions remain server-controlled.
- Saved professional plans can also be discovered through the already allowed
  checklist GET for read-only staff, without requesting owner-only provider screens
  or changing any permission. Saved rows are shown through the existing read model.
- Saved working plans open before remote directory lookup; a repeated open does
  not wait for an unavailable remote catalogue.
- Source IDs/K-Type move to collapsed technical details. Fees remain visible where
  the user must decide about payment. Token shortage has an actionable message.
- The price-confirmation handler retains cost/terms checks and now receives focus
  in the unified flow; cancel returns focus to the initiating control when present.
- Plan changes use existing confirmation and preserve old saved lists/history.
  Previously saved lists remain explicitly selectable, not paid-recreated.

## Changed modules

- `frontend/src/UnifiedCatalogue.tsx`: single orchestration/presentation state.
- `frontend/src/dismantlingFlow.ts`: pure presentation/gating helpers, tested.
- `frontend/src/PlanPartsDonorAnalysis.tsx`: exposes existing flow actions/board;
  no rewrite of paid lookup, recovery or assignment implementation.
- `frontend/src/DismantlingBoard.tsx`: integrated metrics, populated categories,
  selection-dependent toolbar and stale-plan disabled state.
- `frontend/src/unified-dismantling.css`: scoped corporate layout/adaptivity.
- `VirtualDismantling`, `ManagedDismantling`, `pages/Vehicles`: forward existing
  vehicle-edit callback and compact the context in dismantling tabs only.
- `backend/tests/unified_catalogue_server.py`: test harness metadata only, aligned
  with the already existing coverage_verified/taxonomy_status API fields.
  **No backend application/service/API/schema files changed.**

## Verification

Targeted frontend units:43 PASS (flow transitions, separate coverage/taxonomy,
no generation inference, factual labels, category/filter/selection, price guards,
existing billing confirmation separation, modification and retry behavior).
TypeScript + Vite production build PASS. Existing >500kB chunk advisory remains.
No full backend regression was run because backend application logic is unchanged.

Two browser layers at1440×1000 and390×844:

- Presentation matrix:14 scenarios ×2 widths =28 PASS. No modification; selected
  modification/no plan; partial/full Catalogue; saved Plan.Parts; unavailable data;
  insufficient tokens; saved base; saved own plan; partly stocked; stale vehicle;
  limited rights; limited-rights saved professional plan; unreviewed taxonomy.
  Source/auth responses for these states are intercepted fixtures. The one paid
  response is simulated HTTP402; no real provider is called.
- Built UI + guarded local API/PostgreSQL integration: save/reopen, explicit
  one-unit stock receipt, article assignment and separate OEM-cross assignment
  PASS on both widths, with synthetic source data. No external/paid calls,
  no JS errors or horizontal page overflow. Synthetic rows never become proof
  of a real Volvo import or source completeness.
- A96-row saved-plan matrix case verifies search, preview open/close, all-result
  selection count and deselection. Existing preview/mobile focus behavior retained.
- Screenshots inspected and corrected: removed squashed category chips, unused
  zero-count categories and empty bulk-action space; compacted vehicle context.

Commands from `warehouse/frontend`:

```sh
node --test tests/dismantling-flow-unit.mjs tests/vehicle-workspace-unit.mjs tests/bulk-dismantling-unit.mjs tests/parts-tabs-unit.mjs tests/billing-unit.mjs
npm --ignore-scripts run build
WAREHOUSE_E2E=1 node tests/dismantling-flow-browser.mjs
WAREHOUSE_E2E=1 WAREHOUSE_SCREENSHOTS=/tmp/carpot-dismantling-redesign node tests/unified-catalogue-browser.mjs
```

Browser commands require the guarded local test API at8026 and preview5227.
They must never target staging/production. Dedicated DB is localhost55440,
`warehouse_volvo_integration_test`; account/stock writes only in these local fixtures.
Screenshots: [desktop workspace](screenshots/workspace-1440.png),
[mobile workspace](screenshots/workspace-390.png), preparation and partial-plan
screens in the same folder. Machine-readable28-case results: `state-matrix.json`.
Screenshots here are of the actual built interface with clearly synthetic data.
They are not screenshots of Railway or a physical iPhone/Safari.

## Real acceptance gate

No authorized staging browser or Railway connector/CLI is available in this
session. Companion Page supplied no document/URL. Real XC90 source data, deployed
SHA, staging health, paid account behavior and actual staged source integration
were not asserted from local fixtures. Real acceptance remains **UNVERIFIED**.

Before release acceptance, verify the new commit on authorized warehouse-staging
with real saved plans in read-only mode and the confirmed Catalogue status. Do not
activate full coverage from translation or run paid tests to manufacture evidence.
Deployment and real-data receipt/price mutations were not performed in this task.
