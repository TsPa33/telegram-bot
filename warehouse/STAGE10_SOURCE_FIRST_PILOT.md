# CarPot Stage 10 — gated Source-First staging pilot

## Evidence from 2026-11-23 local td1q2018 audit
51 selected source passenger-car modifications / 17 makers; 50 fully measured.
64,393 article identities, 42,843 with OE references (66.53%).
6,146 PRD source types, 4,713 with OE references (76.68%).
30/50 modifications pass >=40 PRD and >=70% type OEM; 12 makers have >=2 good modifications.
The original global rollout acceptance requires 70% of modifications (>=35/50): **not met**.

## Scope
Stage 10 adds an **optional staging-only** gate to the existing automatic
new-donor source catalogue flow. Default OFF. No deployment or variables
changed by this PR. No writes to existing donor plans, stock or invoices.
The existing flow remains unchanged while the flag is off.

Enable only after separate staging read-only verification:
WAREHOUSE_SOURCE_FIRST_PILOT_ENABLED=true

When enabled on staging, automatic creation of a *new and history-free*
dismantling plan requires an exact, pinned modification source snapshot, >=40
PRD source types, complete observed supplier-article records, >=70% PRD types
with OEM, >=65% distinct supplier articles with OEM, and bounded results.
Both review and translated approved PRD types use original product IDs.
Never use a similar-name/other-modification OEM or infer physical VIN fitment.

When the snapshot is incomplete or below threshold, the pilot does not
create a source plan; existing fallback paths remain untouched. The
identity may still be recorded as catalogue evidence, never VIN proof.

## Pending release gates
- Catalogue staging needs to publish verified source snapshots across makes.
- Verify 30 selected source modifications are actually available through the
  authenticated Catalogue API, preserving SHA and source-article completeness.
- End-to-end 3-vehicle staging dry-run, no existing donor migration, no stock writes.
- Legacy donors require a separate non-destructive migration strategy.
- Production, main, PostgreSQL, import-worker, paid VIN providers and live stock
  are out of scope.
