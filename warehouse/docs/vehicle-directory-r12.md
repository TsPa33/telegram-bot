# Vehicle directory R12 — imported by the workspace owner

## Scope and provenance
- Raw source: `FileDbBMG.txt`, Windows-1251; user-supplied. Do **not** commit private source/catalogue payload to the public repository.
- SHA-256 of user's original file: `dd49f6622195226c5e25a02d375dbedf3a2ca1462a42a69621d1ab46892c93e3`.
- Normalized local artifact: `CarPot_vehicle_catalog.jsonl.gz`; 27,108 rows after removal of exact matching source records, 206 brands, 4,350 distinct brand/model pairs.
- Source entries are historical; last first-production year observed is 2018. Unknown end year is **not** current production.
- Data is a suggestion directory, **not** proof of a real donor configuration, VIN identity, part fitment, transmission or original manufacturer approval.

## Deploy and import
1. Deploy the additive migration `d82f73c4a19e` to `warehouse-staging` only and verify API/Web SUCCESS.
2. Sign in as a Warehouse **Director** at `/vehicles`. Expand **Імпорт довідника автомобілів**.
3. Select the provided `.jsonl.gz` (~688 KiB) or original `.txt` (~11 MiB).
4. Click **Перевірити імпорт**, examine counts, then **Підтвердити та додати в довідник**.
5. Check `GET /api/v1/vehicle-directory/stats` from the same authenticated workspace. A different workspace must see none of these private reference rows.
6. Open **Додати автомобіль**; select a make/model/year, and optionally the exact modification.

The import writes only `vehicle_directory_variants` and `vehicle_directory_imports`; never `vehicles`, `parts`, financial or audit records. It is additive and idempotent by account-scoped content identity. A dry-run never commits data.

## Known limitations
- Records with an unspecified end year are candidates, not a verified model-year match.
- Models may include generation/body suffixes; preserve exact source names until reviewed.
- No gearbox data exists in the source; select independently.
- Missing engine codes and repeated marketing descriptions do not imply a verified engine identifier.
- Modern Volvo XC40/XC60 II may need a separate curated supplement; do not invent new year ranges.
- Don't claim completion before actual authenticated upload and read-back of directory stats.
