# Dismantling 2.0 — focused baseline audit / prototype

Base:9631604d47f6101da6d3afd76209ff158ed339c9, verified remote staging source. Previous unmerged PRs retained. No staging reads/writes or owner donors33/34/36 operated on.

- Generator already supplies216 types/227 potential placements without tokens, preview/save/replay preserves protected history. UX defect: large preview and manual save separate the initial action from persisted working list; empty AssemblyTree is mounted before a plan exists.
- `DismantlingBulk.GuidedReceipt` only initializes lines for receipt-eligible IDs. `dismantling_bulk.eligibility` correctly rejects unchecked presence, so selecting227 unchecked rows leads to227 skips. This is a UX gap, not evidence the stock API fails.
- Current receipt transaction already sets dismantled and calls `services.dismantling.receipt`/inventory.stock. Extend this same guarded command with explicit physical confirmation of unknown selected rows, retaining per-batch replay/token/etag, 100-item receipt batches, protected/absent/excluded/archived/sold restrictions. No alternate ledger.
- Preserve damaged state before status=dismantled; never turn known damage into implicit used state. No automatic unit extraction or cost allocation.
- `bulkDismantling.runBatches` checkpoints pending payload/request key; uncertain network failure replays exact pending command. Keep protocol and backwards fingerprints.
- Plan listing/preview currently exposes technical provenance to workspace directors. Platform owner is server-allowlisted via `catalogue_import.platform_admin`, not equivalent to DIRECTOR. Add server response minimization and owner-only source breakdown with unique-position buckets; preserve full stored provenance.
- Reuse current corporate tokens, AssemblyTree, selectors, ledger, plan preview/save. Collapse ancillary controls, preserve selected card/filter/scroll after receipt, add subcategories and one compact selection toolbar.

Prototypes1–3 are illustrative HTML using existing corporate CSS; screenshots captured before final UX implementation. Prototype numbers are examples, not receipts or live QA. No approval/deployment is implied.

Planned commits: A audit/prototypes; B generation/result orchestration and backend source access; C working layout/selection; D explicit physical intake; E isolated regressions/real local-auth PostgreSQL browser; F docs/normal push/Draft PR. No schema migration expected. No deployment in this task.
