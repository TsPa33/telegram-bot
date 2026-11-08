# Volvo deep source audit — verified findings (2026-11-08)

Source: local Windows MySQL td1q2018, user-produced volvo_deep_audit.json. The audit is a READ ONLY indexed/sample scan; no complete production coverage claims.

## Verified relationship samples
- Automobile manufacturer Volvo source ID=120, models.id -> passanger_cars.modelid.
- Volvo XC90 II model_id=13084: 9 distinct modification IDs in source; first example T6 AWD car_id=107555, also D5 AWD id=107556. Duplicate text labels occur for distinct source IDs: use ID + characteristics, not the text alone.
- Volvo XC60 II model_id=37773: 6 modifications; first example 2.0 D4 AWD car_id=126478.
- The returned 67 passenger Volvo models did not include XC40. Mark as unsupported in source; fallback to stored plan.parts or CarPot base. Do not invent variant data or transfer this absence claim to a wider database without checking versions.
- For first XC90 II variant id=107555: passanger_car_attributes=15; passanger_car_trees=245; passanger_car_pds=908; passanger_car_qsi=17.
- For first XC60 II variant id=126478: attributes=15; trees=162; pds=330; qsi=14.
- These are NOT counts of physical dismantled parts. pds rows contain nodeid + productid + supplierid; multiple manufacturers per part type.
- article_links rows for the two variants have linkageid matching selected car_id and observed linkagetypeid=2. Examples also join exactly by supplierid + datasupplierarticlenumber to articles and article_images. Validate linkagetypeid and all relevant joins on the full import.
- Example XC90 II T6 AWD car_id=107555, supplier_id=2=HELLA, product_id=106, article "8GH 008 357-001". articles.NormalizedDescription="Лампа накаливания". article_images contains two distinct picture filenames 2_E325.JPG and 2_M892.JPG; no image bytes or resolved URL.
- prd table has description, normalizeddescription, assemblygroupdescription. Validate mapping article_links.productid -> prd.id and corporate 3-level hierarchy. Retain original source labels.
- Article/OEM via exact supplierId + DataSupplierArticleNumber; Volvo OEM source manufacturerId=120. Priority OEM importer scanned all 499,841 source rows and reported 406,057 new during last full run; this is not the exact Railway total because prior passes inserted links.
- In the first 15 unique sample Volvo OEM-linked articles, 14 have at least one article_images metadata record; this is a biased example, not coverage percentage.
- Additional analogues, attributes and actual images must be validated. TecDoc vehicle IDs are NOT automatically equivalent to plan.parts K-Type.

## Strong architecture implications
1. Keep two independent layers: part-plan coverage resolver and per-field OEM/article/image enrichment.
2. For checked Volvo modifications, use a read-only local source first ONLY where variant + part-tree + article applicability coverage is actually verified. Otherwise saved plan.parts, then paid lookup only after explicit confirmation, otherwise CarPot base. Even if plan source is external, Catalogue may enrich exact article identities.
3. Preserve existing Warehouse part/OEM fields, saved plan.parts receipts, transaction/audit logic, user-uploaded donor photos, corporate Ukrainian normalization and permission checks.
4. Zero silent paid API requests, zero inventory duplicates caused by multiple OEM/aftermarket articles, zero fabricated OEM or fitment, zero broken UX if Catalogue unavailable.
5. Source photos are PictureName filenames; require file resolution and legal usage rights before serving. Image absence produces placeholder, not fake photos.
6. Do not import all 29 other brands. Use Volvo-specific bounded, resumable, idempotent, READ ONLY source importer with destination disk guard, tests and staging-only migrations. Do not touch production.
7. Source audit raw JSON was uploaded in a ChatGPT chat, not automatically committed to GitHub. The Codex task should use this verified summary and request the original JSON if further detailed samples are needed.

## Codex acceptance target
Warehouse Volvo XC90 II, user-confirmed correct source variant + saved or explicit K-Type, stable item categories, exact article->OEM lookup, optional licensed image, one physical stock position per selected part, saved evidence/provenance, reopen without new paid requests. Non-Volvo/XC40 continues to use existing saved plan.parts or base catalogue.

Related context: catalogue/UNIFIED_CATALOGUE_PLAN.md and catalogue/VOLVO_PILOT.md.