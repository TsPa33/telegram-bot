# CarPot Unified Catalogue — implementation contract (Volvo-first)

## Objective
One Warehouse dismantling workflow: select exact Volvo car modification, get canonical Ukrainian part-type list, inspect/assign verified article and OEM cross-references and permitted images, add one physical stock item per chosen type. Other makes must work via existing providers and basic CarPot plan.

## Repositories and isolation
- GitHub: TsPa33/telegram-bot.
- Existing Warehouse branch: feature/carpot-warehouse-mvp; code /warehouse.
- Existing Catalogue branch: feature/carpot-catalogue-mvp; code /catalogue.
- Railway project selfless-caring; catalogue-staging has MySQL 8 + catalogue-api FastAPI (private API plus password-protected /monitor). warehouse-staging is a separate environment with PostgreSQL and Warehouse API/frontend. Production is out of scope.
- Local data source: Windows MySQL td1q2018 (~50.6 GiB). No direct access from cloud Codex/Railway. Source is SELECT-only. The standalone source audit in catalogue/volvo_source_audit.py produces C:\CarPot\Catalogue\volvo_source_audit.json; wait for its real output before asserting source images/fitment.

## Confirmed staging/data
- Source articles exact count: 5,382,176. Article import to Catalogue was interrupted before full completion, with atomic checkpoint for resume; do not call it complete.
- All source manufacturer/model directory rows were imported in earlier sessions: manufacturers 4,375, models 14,945 (validate with live SQL).
- Volvo manufacturerId=120 in source OEM table. Full 499,841 source Volvo article_oe links were scanned in the priority job; 406,057 *new* links were reported for its last full run, not necessarily the unique total in Railway (earlier imports exist). Target brand status marked COMPLETE, but article associations and actual unique row count require auditing.
- Candidate source objects: articles, article_oe, article_cross, article_numbers, article_images, article_attributes, article_links, manufacturers, models, passenger_cars, passenger_car_pds. Previous attempts to read passenger_cars/passenger_car_pds returned MySQL 1146; model fitment remains unproven. Image content, links and rights are unverified.
- Catalogue API: /api/v1/volvo/article?article_number=...&supplier_id=... (requires X-Catalogue-Key). CATALOGUE_API_KEY not configured as of prior check. Private /monitor uses Basic auth. Do not expose secrets to browser; do not make it public without authorization.
- Verified model examples: Volvo XC90 II source model ID 13084; XC60 II ID 37773. These model IDs are not confirmed K-Types.

## Existing Warehouse systems to retain
- plan.parts API with K-Type modification selection and stored lookup results. Article fields article_nr, brand, part_name, optional img_url, characteristics.
- /warehouse/backend/app/api/plan_parts.py (saved categories and articles, paid query controls, selected article workflows).
- /warehouse/backend/app/services/dismantling_workspace.py (read model, source currently base/professional); /warehouse/backend/app/services/virtual_inventory.py (free base); /warehouse/backend/app/services/plan_parts_persistence.py (saved responses).
- /warehouse/frontend/src/DismantlingBoard.tsx and vehicle/parts components, existing Ukrainian translation/corporate category model.
- Vehicle donor photo upload and generic fallback already exist; current Volvo XC60/90 fallback is generic SUV illustration, not model-specific photo.
- Warehouse Part already has article_number, article_brand, oem_number, article_provenance, oem_provenance; Photo/VehiclePhoto exist. Avoid duplicate inventory items or loss of audit/receipts.

## Core rule: two-layer resolution, NOT one exclusive source per car

1. **Plan generation / part types**: prefer saved, VERIFIED CarPot Catalogue vehicle->modification->part-type applicability coverage. If not fully confirmed for selected modification/category, reuse saved plan.parts K-Type result; only if missing and with explicit owner confirmation use a newly paid API lookup. If unavailable/declined use free canonical CarPot base list.
2. **Field enrichment**: even if part types came from plan.parts or base, enrich by exact verified article identity from CarPot Catalogue: supplier-name-to-supplierId dictionary + article-number exact matching (normalization tested). OEM cross-reference is never a proof of fitment. Sources can coexist per field/part.
3. **Images**: user-uploaded donor photo takes precedence over any reference photo. For parts, prefer verified licensed OEM/article image; plan.parts img_url only after rights/availability checks. Missing photos remain labeled placeholders, never fabricated actual images.
4. **Persistence**: snapshots and source/provenance per field; stable identifiers per vehicle/part type; changes to future catalogue do not retroactively overwrite manual or historical data. Reopen saved dismantling without extra paid calls.
5. **Explicit coverage states**: complete_verified / partial / missing / unknown and verified_fitment / cross_reference_only / unverified. Presence of make/model/OEM alone MUST NOT imply availability of a complete vehicle parts list.
6. **No paid surprise**: never trigger plan.parts charge silently or spend tokens on rerender, open, fallback, or "get articles" if already cached. Respect existing roles, budgets, dedup and billing semantics.
7. **Single physical position**: do not create stock quantities from number of manufacturer offers, articles or OEMs.

## Phased implementation
0. Read-only audit of GitHub branches, Railway environments, API schemas, existing migrations, source report; inventory facts vs gaps; check licensing.
1. Define canonical source-independent DTO: vehicle identity, modification reference, part type, category path, catalog article refs, OEM refs, photo reference, fitment status, field provenance, coverage, timestamps and cost status. Plan additive versioned schema migrations; avoid production changes.
2. Implement a server-side CatalogueAdapter in Warehouse with short timeout, explicit auth, per-account isolation; no direct cross-DB MySQL credentials in frontend; fail-closed for security and open to existing saved base UI on service faults.
3. Create resolver orchestrating verified local coverage then cached plan.parts then explicitly confirmed paid request then base, and per-field enrichment. Reuse existing saved structures; no full rewrite.
4. Data import from local source for Volvo only AFTER source audit confirms joins and picture rights: suppliers, OEM, candidate taxonomy, characteristics, analogues, images, variants. Build an idempotent, checkpointed, bounded importer and validate counts. Never mutate td1q2018.
5. Integrate UI into existing dismantling and part cards with source badges, exact modification selection, missing/confirmed photo state, details/assignable OEM and stable stock add, no misleading fitment.
6. Unit/integration tests including negative cases, isolated staging end-to-end XC90 II, manual edits, idempotency, no new paid API calls when cached, no duplicated rows/stock, fallback if Catalogue down, security, rate-limits, rollback.

## Acceptance gates
- Staging only: no production deploys.
- No claimed fitment without evidence matching the exact vehicle variant / K-Type. Do not equate TecDoc model ID with plan.parts K-Type.
- No silent paid API call or automatic debit.
- No third-party image hotlink/redistribution without verified legal rights; store provenance/license.
- 20 exact source article/OEM samples plus negative/ambiguous tests. Source table health errors must be visible, not covered up.
- Maintain the current base and plan.parts behavior until verified local coverage exists.
- Show checks, commit hashes, migration/QA evidence and unverified blockers. Do not declare success on GitHub push alone.
