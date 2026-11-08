# Volvo 107555 — first import corrections

Status: code and local regression checks PASS; prepared for an explicitly authorized
**partial** import only. No import, deployment, push or Railway configuration
changes were performed. Full vehicle coverage is NOT established by these changes.
This report supersedes the initial README's original review/upload procedure.

## Input and evidence boundary

Owner reports successful real Windows export, verified checksum,113 types,
736 unique articles,175 suppliers,459 articles with Volvo OEM,465 with image
metadata and434/434 PDS type/supplier pairs. The full3.34MiB private artifact was
not supplied to this workspace and was not copied into Git.

The supplied minimal `volvo_xc90_107555_product_types_113.json` was read and all113
IDs/names were used for the draft. SHA-256 of that minimal file:
`430887c3e61fafea3249fba692358e6afce51778a40cf74a0232c9c77fc0c718`.
This is NOT the checksum of the full export and must not be passed as its checksum.
Actual full-export checksum validation remains a local Windows preflight command.

## Separate approvals

- `collection_complete`: extractor reached EOF within its bounded source queries.
- `taxonomy_status`: unreviewed/draft/reviewed; covers Ukrainian labels, corporate
  3-level paths and type classifications only.
- `coverage`: partial/complete_verified; full vehicle part-type coverage needs
  a separate explicit review, reviewer, reference, time and source fingerprint.
- A complete PDS/link pair match is relationship evidence, not proof that this
  source contains the whole constructive vehicle catalogue.
- `volvo_review.py --review taxonomy` NEVER promotes coverage. The old combined
  `--confirm-source-links-and-completeness` flag is removed and fails closed.
- Coverage approval uses `--review coverage --coverage-reference ...
  --confirm-vehicle-catalogue-completeness`, separate from a translation command.
  Its fingerprint binds source data, excluding taxonomy annotations. Changed
  article/fitment/source data invalidate the approval.
- Old translation-only `complete_verified` artifacts without this evidence are
  rejected. They must be re-exported/reviewed correctly, not silently trusted.

## Compact persistence / pinned details

Catalogue's `/plan` returns `carpot.volvo.plan.v2` with source car/model ID,
source_snapshot_sha, observation date, compact modification reference,
coverage/taxonomy statuses and type rows (labels, paths, kind, article_count).
No article lists, OEMs, crosses, raw PRD rows, characteristics or image metadata
are stored in a new Vehicle plan. Persistence uses an allowlisted projection;
extra source blobs cannot leak into the vehicle JSON or its audit snapshot.
Warehouse validates the compact projection and caps it at512KiB.

Raw data live once per version in new MySQL `catalogue_volvo_versions`, keyed by
(car_id, SHA-256), inserted immutably. Existing latest-directory table
`catalogue_volvo_snapshots` stores only compact metadata and the raw version pointer.
This is additive MySQL DDL in `volvo_integration.sql`, not executed here. No new
PostgreSQL migration: sole packaged Warehouse head remains `e641b3a20f97`.

Article detail requests use the saved car ID, product ID AND source SHA. Catalogue
never substitutes latest data for a missing pinned version. Warehouse verifies
response identities/count and fails with an explicit503 when details are missing,
without a paid retry or changes to Part. Article/OEM assignments use that same
pinned result and record raw source SHA in provenance. Characteristics, crosses
and image metadata are returned from the server; filenames do not become photo URLs.

Reopening the plan/listing needs only PostgreSQL. Detail outages do not erase the
plan. Existing legacy raw plans remain readable; no automatic rewrite/backfill
or cleanup of existing donor data was performed.

Generated size regression (NOT measurement of the private export):
3,802,452-byte synthetic source ->14,563-byte compact113-type projection;
with the actual Ukrainian draft annotations ->44,954 bytes. The test contains
synthetic numbers/supplier data and public type labels, never private OEM records.

## Ukrainian draft

- [Review table](review/TAXONOMY_DRAFT.md)
- [Machine-readable mapping](review/volvo-107555-taxonomy-draft.json)

All113 IDs are present and all original labels retained. Preliminary classes:
64 `part`,37 `consumable`,9 `equipment`,3 `review`.
Every row is explicitly `draft`, not approved. Same-text IDs are never merged.
Truncated322, unspecified1165 and ambiguous5025 are `review`.

100 paths are complete under the existing corporate sections/subsections.
13 paths intentionally retain a null category/subcategory requiring editorial
resolution:105,112,251,273,322,387,794,1080,1092,1165,2462,3229,5025.
Examples: the existing taxonomy has no general suspension-arm subgroup and cannot
assign front/rear without evidence; some bulbs have no indicated front/rear position.
We did not invent positioning or add independent categories to disguise these gaps.
A fully approved taxonomy requires resolving these entries first. The raw partial
source import is independent of this editorial work.

`catalogue/carpot_taxonomy.json` is a deployment snapshot of Warehouse's existing
SECTIONS/SUBCATEGORIES, not a second authoritative taxonomy. A regression test
requires exact equality with that source. Review validates both section and subgroup.
New `equipment` classification is supported in the existing board; non-part types
cannot pass the Catalogue physical receipt route without separate validation.

## Selective upload gates

The first-import allowlist is exactly `{107555:13084}`. Other car IDs cannot upload.
The loader reads ONLY `output/107555.json`, never every JSON file in the directory.
It verifies bounded file size, canonical payload SHA-256 against the operator's
independently verified expected hash, envelope hash, exact car/model/modification
identity and expected coverage. Invalid legacy approval or a different coverage
state aborts before target writes. The uploader rechecks identity/hash too.
Upload does not connect to the Windows source or re-export data.

### Read-only Windows preflight — safe to run first

In a checkout of this local integration commit, from `catalogue`:

```powershell
# Use the already verified envelope SHA of the FULL export.
# This is canonical payload SHA-256, not Get-FileHash of the pretty JSON wrapper.
$expectedSha = Read-Host 'Verified full export envelope SHA-256'
python .\volvo_vehicle_import.py --validate-upload --car-id 107555 --expected-sha256 $expectedSha --expected-coverage partial --output .\volvo-export
```

This command opens NO database connections and writes nothing. It should report
113/736/175,459 OEM-bearing articles,465 image-metadata articles and434 matched PDS
pairs out of434; coverage remains partial. Compare the actual output before approval.
No private records need to be pasted into chat.

### Future import — documented only, NOT executed/authorized by this report

After separate approval and verification of the catalogue-staging MySQL tunnel,
review/apply the additive DDL with the existing guarded target helper. It creates
three tables if missing and never alters stock/finance. Existing tables are retained.
Then use the SAME verified full-artifact hash and a dedicated output folder:

```powershell
python .\volvo_target.py --confirm-staging --apply-additive-schema
python .\volvo_vehicle_import.py --upload --confirm-staging --car-id 107555 --expected-sha256 $expectedSha --expected-coverage partial --output .\volvo-export
python .\volvo_target.py --confirm-staging
```

No production connection is allowed. DEST_* stay private and must refer to the
separate catalogue-staging tunnel. No source password is required for upload.
Repeated same-SHA upload cannot duplicate a raw version; newer versions retain
old pinned data. Imported latest data remain partial and cannot masquerade as
full vehicle coverage. Existing saved Plan.Parts and free base fallback remain;
new paid requests still require the existing explicit confirmation.

### Later taxonomy review — offline only

Resolve the13 missing paths and review every draft class/label first. Work on a
copy of the export; this changes metadata and produces a NEW canonical SHA.

```powershell
python .\volvo_review.py .\volvo-export\107555.json --review taxonomy --mapping ..\warehouse\docs\unified-catalogue\review\volvo-107555-taxonomy-draft.json --reviewed-by 'OWNER_REVIEW_REFERENCE'
```

With the current unresolved draft this must fail, rather than approve invented
categories. Once valid it still leaves coverage=partial. Review vehicle coverage
only after obtaining independent evidence; do not use a translation or434/434
pair comparison as that evidence. Any subsequent upload must pin the new SHA.

## Tests and limits

- Warehouse targeted PostgreSQL tests:42 PASS, plus1 new cross-module compact
  wire-format test PASS (30 unified cases +13 existing checklist/recovery cases).
- Catalogue tests:15 PASS, including generated113/736/175/459/465/434 shape,
  separate approvals, stale evidence, compact size, immutable/pinned versions,
  allowlist/stray-file/SHA/status gates and a zero-connection preflight.
- Frontend targeted units:17 PASS; TypeScript/Vite build PASS.
- Chromium1440/390: PASS against guarded local PostgreSQL + synthetic provider
  harness, including save/reopen, receipt, article/OEM selection; no paid/external
  requests, JS errors or horizontal overflow. This is not staging acceptance.
- No real MySQL DDL/import integration run, no full private artifact parsing here,
  and no real Railway checks/deployments. Those results remain UNVERIFIED.
- Existing chunk-size advisory and TestClient deprecation warning remain non-fatal.

Readiness: the selected original partial export can be validated/imported through
the guarded procedure after authorization. Full Catalogue plan activation remains
blocked by independently unproven vehicle coverage and the unfinished taxonomy
review. Photos are metadata-only and are not a blocker for either operation.
