# CarPot MVP · Stage 2 + Stage 10 integration checkpoint

Date: 2026-11-23

## Input
- Accepted code baseline: Stage 2 PR #575, SHA `90b4370ab28b8da66adb32dae980e941aeb43399` (9/9 GitHub Actions successful).
- Ported optional pilot rules and offline fixtures from Stage 10 PR #574, SHA `ef347425ad2371ed465cb5df80b90d6aee2e3b90`.
- Integration draft branch: `feature/carpot-stage2-stage10-mvp-integration-20261123`.
- Base PR: `feature/carpot-versioned-catalogue-binding`; no merge to `main`.

## One-writer contract
- Stage 10 only assesses whether a new donor with no plan/stock/history has a qualified
  complete modification snapshot: >=40 source PRD types, >=70% types with OEM,
  >=65% distinct supplier article keys with OEM, bounded results.
- Reuses `unified_catalogue.persist()` from Stage 2 exclusively.
- Source PRD identities and `source_snapshot_sha` are preserved unchanged.
  `digest(pilot_payload)` describes only the filtered local projection.
- Excludes equipment, unlinked and zero-article rows from created plan.
- Existing donor plans, receipt, stock, manually confirmed OEM and physical OEM untouched.
- Pilot OFF keeps the pre-existing automatic plan path. Pilot ON is staging-only
  and fails closed on incomplete batches or malformed evidence.

## New acceptance checks
- Explicit OFF regression: review-only types without source-fitment flag do not
  create plan or stock.
- Explicit ON single-writer regression: exactly one call to `persist` with
  50 selected products, original source SHA and 50 versioned bindings.
- Existing Stage 10 pure gate/coverage tests and Stage 2 binding/receipt tests.

## Outstanding release gates
- Full GitHub Actions on **this integration SHA**: pending.
- Oracle `article_links` secondary-index rebuild and 60/60 source validation:
  independent ongoing operation; do not interrupt.
- Read-only Catalogue snapshot proof for supported modifications: pending.
- Staging-only three-vehicle acceptance and coverage report: pending.
- No paid VIN API, DB schema/variables/production changes, no stock writes.

Rollback: retain source history, do not deploy an older client unaware of active
Stage 2 bindings without a verified compatibility plan.
