# CarPot Master Parts Catalogue v0.2 — preview candidate

Base verified on GitHub: Warehouse draft PR #583, head `810a767a69c4633983f0a51412ee92abf3f4daa6`. This is a pure candidate engine, not a replacement for the Warehouse generator, and is NOT wired into runtime or deployed. No database writes, migrations, API calls or stock edits.

## Reproduce

Run `python -m unittest -v test_master_parts` and `python audit.py /path/to/carpot-prd.csv`. The latter requires the original CSV with SHA256 `37544991ebb1e6b6dd758bcd3ab24bafb7e81a9c933b19c15ce86f26091bf264`. The generated inventory retains every source field and ID; mapping is candidate-only. `audit_summary.json` and `preview_*.json` are synthetic test fixtures, not live vehicle plans. Audi/Volvo use the known source product IDs from v0.1 but an illustrative SUV profile, not verified vehicle attributes. DAF/BMW live per-position coverage is not measured. The source data is kept outside the repo unless explicitly authorized. No full classification or ≥90% OEM coverage claim.

## Integration contract and blockers

`app/services/unified_catalogue.py::persist` currently stores exactly one `car:<car_id>:product:<product_id>` row and updates `plan_item_binding.py` by product. `workspace_entries` and `row_product_id` depend on that key. `auto_oem.py::placement_ok` currently recognizes front/rear/left/right but not numbered axles/doors/ordinals. Do NOT encode physical rows by appending to this legacy key or pass unplaced candidates to the auto-OEM worker. Existing `canonical_rules`, `dismantling_plan_v3`, `vehicle_configuration`, and `dismantling_preview` are the integration target, not a parallel persistent store.

Use canonical type + existing placement IDs (with precise side, door, axle, ordinal), retain source identity `(kind, manufacturer_id, model_id, car_id, snapshot_sha)` and exact PRD evidence separately. Confirm topology and counts from structured vehicle/configuration sources or explicit inspection; don't infer 4 side doors from SUV alone. An unresolved source row remains intact; the preview marks candidate physical rows `reconcile` rather than creating duplicate generic and specific entries. Existing manual or stock rows are protected. `proposed_oem` is a read-only candidate only when a verified exact-identity article actually lists that OEM and normalized position proof; the live source adapter must build and validate those normalized fields. Do not interpret this as verified VIN-fitment.

Future integration: map candidate seed to canonical types/taxonomy; review candidate PRD semantics and unknowns; produce source-driven profiles; reconcile old generic rows by preview and explicit approval; test aggregate vs component receipt/exclusion; integrate new donor flows (VIN/catalogue/manual) in the existing v3 generator and receipt path; run isolated PostgreSQL CI and staging QA, then stage only after approval. No production/main/Oracle schema/import-worker changes.
