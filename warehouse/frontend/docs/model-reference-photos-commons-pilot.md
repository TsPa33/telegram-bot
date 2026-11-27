# Wikimedia Commons pilot — 2026-11-26
Candidate on PR #588. No live download, segmentation, deployment or asset publication.
 
## Flow
Use operator CLI discovery for distinct active model identities (no VIN or tenant IDs). It queries Commons Action API generator=search with bounded metadata, accepts only explicit CC0 / CC BY / CC BY-SA 3.0 or 4.0, checks URL, author, restrictions, revision and raster MIME. Search results are not model identity evidence. Review the exact photo/model/year and the full file page including noncopyright restrictions and required credits; record approved identity, title and SHA-1 in a persistent reviewed registry. New models not yet reviewed stay pending, without burning attempts. Existing worker processes approved entries automatically and reuses cached exact identities. Fully unattended discovery/review for new identities is not implemented. The user never has to upload photos in Warehouse.
 
Run from warehouse/backend:
```sh
export WAREHOUSE_COMMONS_USER_AGENT='CarPot/1.0 (https://github.com/TsPa33/telegram-bot)'
python -m app.services.commons_model_photos "Volvo" "XC90" --year 2016
python -m app.services.commons_model_photos "DAF" "XF 105" --year 2007
python -m app.services.commons_model_photos "Alfa Romeo" "147 (937_)" --year 2008
python -m app.services.commons_model_photos "Audi" "Q5"
```
Review registry JSON: array of records with identity (manufacturer,model,generation,year), title (exact File: title), sha1 (from live API), reviewed=true. No fabricated revisions or approval bundled.
 
## Local cutout
Optional CPU ONNX runtime + numpy in a separate test environment. U2NET/U2NETP-compatible 320x320 model chosen for pilot instead of heavier BiRefNet; use only an independently verified commercial-use-compatible checkpoint with documented provenance and SHA256. No auto-download. Check preprocessing/output against selected model before release. Revalidate source revision and hash, run segmentation, then existing WebP alpha checks and store credits. Inspect actual masks for wheels/mirrors and distracting backgrounds before live acceptance. Need separate compute/resource test before enabling alongside Warehouse.
 
## Deployment gates
Existing WAREHOUSE_MODEL_PHOTO_ENABLED and staging-only persistent directory plus WAREHOUSE_MODEL_PHOTO_PROVIDER=commons, WAREHOUSE_COMMONS_APPROVED=true, WAREHOUSE_COMMONS_REVIEW_REGISTRY, WAREHOUSE_COMMONS_USER_AGENT, WAREHOUSE_CUTOUT_MODEL_LICENSE_APPROVED=true, WAREHOUSE_CUTOUT_ONNX_PATH, WAREHOUSE_CUTOUT_ONNX_SHA256. Dependencies not added to existing Warehouse lock or deployment: numpy and onnxruntime must be pinned/tested for pilot first. No paid API, token or provider account. Local tool environment DNS failed for commons.wikimedia.org, upload.wikimedia.org, github.com; onnxruntime/rembg absent. No actual image or model download verified. Run fixture tests, full CI, source review, CPU benchmark, four visual pilot examples and then existing donor coverage. Do not enable or deploy until passed. No production, stock, billing, OEM or PostgreSQL write.
 
References: https://www.mediawiki.org/wiki/API:Imageinfo ; https://www.mediawiki.org/wiki/API:Etiquette ; https://github.com/xuebinqin/U-2-Net ; https://github.com/danielgatis/rembg (model weights have independent licensing).
