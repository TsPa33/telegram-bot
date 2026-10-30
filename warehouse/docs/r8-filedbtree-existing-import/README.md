# R8.5 — FileDbTree using existing account-local JSON import

## Status
Draft PR #392. **NOT deployed. NOT merged. Tests not executed in a real PostgreSQL test environment.**
No stage/production data modified, no stock or financial writes.
Use **`/api/v1/dismantling/catalog/import?dry_run=true`** for preview and explicit POST without `dry_run` only after review and licensed access confirmation.

## File
`carpot_volvo_465.json` (distributed outside GitHub):
- 465 distinct part-type names
- 919 explicit candidate model associations
- Volvo XC60: 368; Volvo XC90 I: 419; Volvo XC90 II: 132
- `rights_confirmed:false` deliberately requires user confirmation, not editing to true automatically
- No price/OEM or exact variant fitment claims
- Some source vocabulary uses mixed transliteration/Russian and remains unverified; no invented translation

## Contract
`types[].applicability`: optional, nonempty (if supplied), up to 20 objects:
`{ "manufacturer": "Volvo", "model": "XC90", "generation": "II" }`.
Absent/null = legacy account-wide catalogue (backward compatibility).
Explicit model associations are **candidate coverage only**, never verified compatibility by VIN, engine or trim.

## v3 integration
- Account-local candidate source is separate from global published canonical rules.
- Model-scoped types appear in v3 preview and deliberate plan generation as **unknown**.
- Source references stable `local:<source.id>:<catalog_key>`.
- Deterministic IDs; repeated import should not duplicate types or plan placement.
- No amount, stock receipt, OEM, price or supplier observations generated.
- Existing v3 plan is flagged as changed when model-relevant local catalogue changes.
- Existing imported account-wide types retain previous legacy behavior.
- Imports do not rewrite existing vehicle plans. User must refresh deliberately.

## UI
Admin -> Catalogue -> Import -> **Імпорт конструктивних типів запчастин**
is a separate account-local JSON widget, not the existing market CSV importer.
Source import widget remains available from the legacy Vehicle -> Popередній довідник area.
After selecting JSON, confirm legitimate storage rights, run preview, review, then explicitly confirm import.

## Validation before staging merge
From repo root, on an isolated PostgreSQL test database:
```bash
cd warehouse/backend
python -m alembic upgrade head
python -m pytest tests/test_dismantling_v2.py tests/test_dismantling_plan_v3.py tests/test_dismantling_preview.py -q
python -m pytest -q
cd ../frontend
npm ci
npm run build
```
Also run browser viewport regressions, migration checks on a populated synthetic database, and verify v3 preview/saved plan for XC60, XC90 I, XC90 II, and non-Volvo vehicle.
Do not assume these commands were executed as part of the PR preparation.

## Caveats
- The same part name across models is stored once in the 465-type JSON input but multiple `applicability` associations are maintained.
- Unknown exact generation on a vehicle must not imply XC90 I or II.
- Real stock and sales are independent.
- This is **workspace-local**, not a global publisher; separate governance is required for platform-wide canonical catalogue.
