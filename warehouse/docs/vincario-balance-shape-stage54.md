# CarPot Checkpoint №054 — Vincario API Decode balance audit

Date: 2026-11-19

## User-reported situation
- Vincario pricing lists Free Demo **up to 20** VIN Decode API calls, 5 Vehicle Market Value and 5 Stolen Check.
- Actual CarPot API 3.2 balance result returned Vehicle Market Value=5, Stolen Check=5, OEM=0, OEM History=0, but **no API Decode field**.
- This does not establish VIN Decode=0 or free trial activation. Do not call `decode` or purchase paid package yet.

## Findings
- Railway staging `telegram-bot` has names `WAREHOUSE_VINCARIO_API_KEY` and `WAREHOUSE_VINCARIO_SECRET_KEY`. Secrets were never printed.
- Stage #053 parser in `warehouse/backend/app/services/vin_vincario_balance.py` recognized only literal `API Decode`, and hid all unrecognized balance fields. Therefore it could not tell absent key from alternate naming.
- No raw API balance body was stored; therefore must perform a new balance-only call for exact structure.

## Implementation #054
- Parser explicitly returns VIN decode status (`available`, `not_returned`, `unexpected_value_type`) and distinguishes missing from numeric zero.
- Accepts limited decoder field aliases (`API Decode`, `API VIN Decode`, `VIN Decode`, `VIN Decoder`, `API VIN Decoder`).
- Reports only short, safe field **names and coarse types**, never field values, API key, secret, VIN, raw JSON, or unrestricted keys.
- Frontend admin technical details shows explicit VIN decoder status and safe field inventory.
- Offline regression tests cover missing/zero/alternate keys and secret suppression.
- All live VIN lookups, 50 UAH Billing, `WAREHOUSE_VINCARIO_ENABLED` remain unchanged.

## Next action
1. CI green -> staging backend and frontend.
2. User manually clicks `Vincario: перевірити API-баланс` once.
3. Interpret sanitized provider field names and numeric VIN Decode credits (if present).
4. Verify Free Demo activation **separately** before triggering any VIN Decode.

## Deployment evidence
Fill with actual SHA, CI IDs, backend/frontend Railway deployment IDs and statuses at completion. Production untouched.
