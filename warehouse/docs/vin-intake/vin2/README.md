# VIN 2.0 — 2026-11-11

Base: `bf4712b01627af3a3d752a32dc3cea4ba005917b`, branch `feature/assembly-component-inventory`. VIN intake only; no catalogue generation, new tables or migrations.

## Functional changes

- Bounded mapping of **57 useful vPIC fields**: 31 primary keys plus structured technical attributes (manufacturer company, displacement cc, valve train, turbo, cooling, brakes, wheelbase/wheels, seating, battery/charging, TPMS/ABS). This is mapping capacity, **not 57 facts guaranteed per VIN**. Fields not explicitly returned remain unknown.
- Fuel secondary, electrification, transmission speeds, engine manufacturer/configuration/injection, series/trim variants, plant and market retained. EngineModel remains a description; only explicit EngineCode/TransmissionCode/Generation labels populate those keys. Series never becomes generation automatically.
- FreeVINDecoder attempted once when important fields remain unknown, even if model/year/engine/transmission are present. Robots policy is required; denied/inaccessible policy stops collection. Policy timeout 4s, page 7s, bounded response, crawl-delay/rate gate. No Vincario/paid calls, no captcha/auth/proxy bypass.
- Combined cache: 5 minutes for a reported result, 30 seconds for empty/unavailable results, bounded 128 VINs, same-VIN serialization, copied results. Process-local cache; replicas may each make an initial request. Free provider policy/results also bounded/cached. No infinite retries.
- First source remains primary; conflicts and source of each field retained. Additional attribute conflicts retain alternative value/source without overwriting. Numeric equivalents such as 2 and 2.0 do not create false conflicts. Oversized source strings are not truncated into codes.
- Central backend Ukrainian normalization: drive, transmission, body, fuel, electrification and common technical terms. Plant designations, VIN and engine/transmission identifiers remain unchanged. Frontend no longer extracts/normalizes drive codes; VehicleInput uses the same backend mapper.
- `vin_details` retains primary values, decoded snapshot, provenance/conflicts, structured `additional` and `decoded_additional`. Existing snapshots are read unchanged; trust remains user-confirmed/reported, not factory verified. Core Vehicle fields retain their existing roles.

## Mobile form

Compact summary first: make/model/year, modification, body, engine, fuel, transmission and drive. Known fields appear in five groups (vehicle, engine, transmission, body, additional). Two-column compact controls; empty optional fields are inside collapsed **«Потребує уточнення»**. Three essential manual fields remain visible when not decoded. Every supported value can be edited; confirmation resets after edits. Each value shows source or manual change; conflicts remain visible. Existing corporate tokens/navigation unchanged; CSS scoped to `.vin-intake`.

[Mobile summary](screenshots/vin2-mobile.png) · [Collapsed clarification section](screenshots/vin2-mobile-clarification.png). Screenshots contain clearly labelled OFFLINE TEST fixtures, not live VIN specifications.

## Actual external attempts for the two requested VINs

Performed real lookups through the adapters, not fixture calls. Both primary requests were unavailable from this execution environment; FreeVINDecoder policy could not be obtained. No source vehicle specifications were received. [Captured results](evidence/live-attempts.json).

| VIN | Useful attributes actually received in Codex | Catalogue-useful received | Important fields undefined | Conflicts found |
|---|---:|---:|---:|---:|
| YV4L12RK6N1970668 | 0 | 0 | 13 | 0 |
| YV4A22PK2G1092943 | 0 | 0 | 13 | 0 |

These zeros measure this failed access attempt, **not the amount of data available for the vehicle**. Zero conflicts with no data does not confirm consistency. `nhtsa_nonempty_fields` is unavailable because no response was received. `undefined_important` uses a fixed documented important-field set, not an inferred complete build sheet. New API also reports missing supported fields separately. Generation, factory engine/gearbox code, exact trim and market remain unknown without explicit source evidence; they are never inferred from expected Volvo models.

This does not prove provider access fails from Railway. No staging test donors created; actual live characteristics and field counts must be checked in the deployed form. No test values were promoted into the captured live results.

## Checks and staging

Targeted backend decoder/enrichment/cache/robots/normalization/persistence and existing VIN tests: **20 PASS**. TypeScript/Vite **PASS**. Local browser **PASS**. Results in `evidence/`. Browser: both requested VINs with explicitly offline responses + real isolated local PostgreSQL; autofill/manual editing/save/reload/duplicate, additional JSON attributes and mobile 390px layout. This is not live provider evidence or staging QA. Build uses TypeScript + Vite directly; no repeated full regression suite.

No migrations. Existing Alembic head remains `08b72c9d4e16`. Local tests use only dedicated localhost:55441 `_test` databases. No production/staging data mutations or catalogue/stock operations.

Authorized Railway connector/CLI/credentials are unavailable in Codex. Push is to the actual staging source branch supplied by the owner. Existing Auto Deploy is expected to build API/Web; its result cannot be claimed without Railway access. Use the owner-connected Railway to verify both active deployment SHAs match the new commit, API startup/health and form, then obtain live counts. No manual redeploy or Variables changes attempted.

Application supplied by owner: https://confident-sparkle-warehouse-staging.up.railway.app . Deployment and live browser acceptance remain UNVERIFIED in this session.
