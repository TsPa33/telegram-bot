# CarPot Volvo-first integration pilot

## Target acceptance scenario
A CarPot Warehouse user chooses Volvo -> model -> generation -> year -> specific K-Type modification, opens a saved dismantling plan and sees categorized part types. A selected physical part can display a verified aftermarket article, verified OEM cross references, and a licensed part photo if present. The vehicle photo is uploaded by the user or comes from a verified licensed source; otherwise a clearly marked generic fallback is shown. Parts can be added once, edited, and reopened without re-paying for already saved plan.parts data.

## Grounded current facts
- The local MySQL database td1q2018 has a confirmed Volvo manufacturerId of 120, 499,841 OEM references in article_oe, articles, manufacturers and models. The full Volvo OEM import was completed to isolated Catalogue staging.
- The existing Warehouse plan.parts integration already has K-Type modification selection, saved part types, Article.article_nr, Article.brand, optional Article.img_url and characteristics.
- Warehouse parts already have article_number, article_brand, oem_number and separate provenance fields; it already has part photo and user vehicle photo functionality.
- The current Volvo XC60/XC90 vehicle fallback artwork is generic SUV body artwork, NOT an actual Volvo model photograph.
- The previous local passenger_cars / passenger_car_pds reads failed with MySQL 1146. True per-model fitment from local DB remains unverified.

## Source-data discovery (read-only first)
Run volvo_source_audit.py on Windows. It records source schema, columns,
indexes, small samples and errors in volvo_source_audit.json. Inspect the
following relationship groups BEFORE any new import:
1. Supplier / spare part brand: mapping article supplierId to verified name.
2. Part taxonomy: category / generic part type / parent path relationship.
3. Vehicle modifications: make, model, period, engine, K-Type equivalent or
   separate vehicle identifier and fitment relationship.
4. Part OEM links: exact supplierId + DataSupplierArticleNumber matching.
5. Analogue/cross numbers: article_cross and article_numbers.
6. Part attributes: article_attributes and units.
7. Part photos: article_images and any related file/URL references. Determine
   if bytes or links are present, whether they resolve and legal usage rights.
8. Vehicle photos: licensed or user-owned source, fitment of image identity,
   no generic body artwork misrepresented as an exact vehicle photo.

## Integration contract, staging only
- Do not change the existing plan.parts dismantling selection or billing.
- For lookup by aftermarket article, require BOTH a verified supplier-name-to-ID
  mapping and an exact article number (normalized by documented rules).
  A vehicle manufacturer ID is NOT a supplier ID.
- OEM cross reference is NOT proof of compatibility to a chosen VIN/K-Type.
- Store per-field provenance, retain manual values, never automatically overwrite
  manually entered OEM or pictures.
- Every physical stock part is one stock position; many OEM/cross numbers never
  create multiple physical parts. Maintain duplicate guards.
- Warehouse will call Catalogue API server-side with a separate key and a
  short timeout. API failures fall back to existing saved plan.parts data.
- No Railway production deployment and no Warehouse staging migration until
  sample mappings, local source rights and compatibility rules are verified.

## Acceptance tests
1. Volvo XC90 II, specific K-Type: persistent dismantling plan reopens with no
   additional paid provider call for already stored results.
2. Twenty source-grounded article examples: exact brand/number match,
   cross-reference OEM, and negatives that must NOT match.
3. Source image URLs or bytes resolve, commercial rights are documented;
   missing image yields placeholder instead of a guessed asset.
4. Vehicle photo upload remains primary and persists.
5. No duplicates when adding physical positions for the same part with
   multiple articles or OEM values.
6. Read-only audit never mutates local td1q2018.
7. Catalogue and Warehouse remain isolated until staging QA passes.

## First action
Existing PowerShell with local SOURCE_* environment variables:

    cd "C:\CarPot\Catalogue"
    Invoke-WebRequest -Uri "https://raw.githubusercontent.com/TsPa33/telegram-bot/feature/carpot-catalogue-mvp/catalogue/volvo_source_audit.py" -OutFile "volvo_source_audit.py"
    python -u .\volvo_source_audit.py

Review the saved C:\CarPot\Catalogue\volvo_source_audit.json before creating
any new importer or activating Warehouse integration.
