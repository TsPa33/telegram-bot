# VIN-only staging release candidate — 2026-11-11

**Deployment BLOCKED: no authorized Railway access. This is a prepared candidate, not a staging release confirmation.**

## Candidate

- Repository: TsPa33/telegram-bot.
- Branch: `release/warehouse-vin-staging`.
- Base: `76e3d7519af5d2eace89f882cfb2e11ecd3126a7` (`feature/assembly-component-inventory`). This is a compatible **repository base, not a verified deployed staging SHA**.
- VIN-only commit: `7659c04` (clean cherry-pick of `f8586ff6e1388603ccde67b261121521241e2909`). Subsequent commit only adds this release guide and evidence.
- Diff against that base contains the 22 VIN files only; no universal catalogue implementation, classifications, canonical publishing or plan reconciliation added.
- `f6cf63bc4f7e138ae87ae2a33e1ebbe046c6bd2e` is NOT an ancestor; `universal_catalogue.py`/`UniversalPlanReview.tsx` are not included by the VIN cherry-pick. Do not merge the full universal-catalogue feature branch to release VIN.

Review: https://github.com/TsPa33/telegram-bot/compare/feature/assembly-component-inventory...release/warehouse-vin-staging

## What is actually verified

| Check | Result |
|---|---|
| Git transport access | Available; branches fetched |
| Railway tool/CLI/token | Unavailable; presence checked without printing values |
| Actual project/environment isolation | UNVERIFIED |
| API/Web source branch and active SHA | UNVERIFIED |
| Current staging Alembic revision | UNVERIFIED |
| Staging site URL | UNVERIFIED; not guessed |
| Candidate frontend tsc/Vite build | PASS; no repeated large suite |
| Candidate local full browser flow | PASS for both requested VINs, offline decoder fixtures + real dedicated local PostgreSQL |
| Duplicate VIN protection | PASS in the same candidate browser run |
| Candidate packaged Alembic heads | Single `08b72c9d4e16`, parent `f7a10b8c43d2` |
| Runtime staging startup, migration, health | UNVERIFIED; not run |
| Live decode | BLOCKED by previously observed CONNECT 403; no retry loop or proxy bypass |

Local browser used the candidate's own API (`127.0.0.1:8032`) and own compiled frontend (`127.0.0.1:5232`), dedicated localhost `_test` PostgreSQL only. Registration and two donors were created only inside that isolated local test workspace. No staging donor was created. Decoder fixtures are explicitly OFFLINE TEST data, not facts about those VINs. Existing local targeted backend tests from the source VIN commit are documented in README; they were not all repeated here.

## Important dependency gate

`warehouse/deploy/railway/services.json` is explicitly a **checklist**, not live configuration. It suggests `feature/carpot-warehouse-mvp`. GitHub currently has that branch at `cc41f7e3cf13a4b61ee5d5c74ef20626089f6d3c`, whose migration graph does **not** include `f7a10b8c43d2`.

Therefore a blind cherry-pick of only `08b72c9d4e16` onto that MVP branch will have a missing parent. Copying the entire universal feature or changing the parent under an already published revision ID is not a safe fix.

This candidate deliberately uses the existing compatible Assembly base and excludes new universal work. **If actual staging uses the older MVP base, do not deploy this candidate as though it were a VIN-only diff against staging**: that would also introduce earlier Assembly/global workflow changes. Stop and review the actual base/dependency scope first. Likewise, do not replace a newer staging deployment with this older base and lose its fixes.

## Concrete release path using Railway Console + GitHub

No new GitHub Actions workflow was found in this repository. Use the existing GitHub-linked Railway Auto Deploy, after the following checks in the owner's authorized session:

1. In Railway open **selfless-caring → warehouse-staging**. Verify environment ID `e9d04365-fc5a-4ba2-84a7-275c44580fe8` and project ID `ff2f3a14-2ffa-49ba-9b9d-9889ce98da5d`. These are expected IDs from the task context, not newly verified here. Confirm separate staging PostgreSQL bindings and volumes. Do not open production for operations.
2. For **telegram-bot** (API) and **confident-sparkle** (Web), inspect Settings → Source: actual GitHub branch, Root Directory, Dockerfile; inspect latest active deployment full commit SHA. Record both; branch names alone are insufficient. Confirm Auto Deploy/watch paths target Warehouse.
3. Read staging Alembic revision via an authorized **read-only** connection. Expected compatible parent is `f7a10b8c43d2`, or the same `08b72c9d4e16` if already applied. A different/newer/divergent revision requires review; no migration command or downgrade should be run to force compatibility.
4. In GitHub compare the release branch with the **actual linked source branch** from step 2. Proceed only if the baseline is compatible and the release introduces solely the reviewed VIN patch, with no loss of current fixes. If there are extra catalogue/Assembly changes or missing migration dependencies, **STOP**; supply the actual branches/SHAs/revision to prepare the correct minimal backport. Do not merge the entire universal feature.
5. If the gate passes, use a reviewed PR of the VIN patch into the actual staging-linked branch. This preserves Railway bindings and Variables. Alternatively, the authorized owner can deliberately select this isolated release branch for only the two staging services, but only after the same baseline gate. No such binding change or PR merge has been performed by Codex.
6. Let the API deploy via the existing Dockerfile/start command **`python -m app.staging`**. It calls `migrate(timeout)` under `MIGRATION_LOCK`, then `command.upgrade(config, 'head')`, and starts serving only after completion. `08b72c9d4e16` adds only nullable `vehicles.vin_details JSON`, no backfill, no inventory/finance changes. **Do not run Alembic manually a second time.**
7. Wait for API SUCCESS, startup log migration completion and `/health` 200. Verify Alembic head `08b72c9d4e16` read-only. Verify Web SUCCESS and both active deployment SHAs equal the intended release head. If either failed, collect logs and stop; do not auto-downgrade, drop evidence columns or clear data.
8. Open **confident-sparkle → Networking → existing public domain**. This is the correct way to obtain the actual CarPot URL; no URL is invented here. Confirm session reaches warehouse-staging.

No Variables, Dockerfiles, service bindings, worker, production or database were changed as part of preparation. Auto Deploy can also trigger other services if they watch changed backend paths; inspect their watch patterns before publishing to a linked branch rather than assuming only Web/API will deploy.

## Acceptance in the actual browser after deployment

Use an explicitly isolated test workspace, not the working donor workspace. Decoder lookup may be read-only, but clicking save creates Vehicle + its audit Operation.

For **each** `YV4L12RK6N1970668` and `YV4A22PK2G1092943`:

1. Автомобілі → Додати автомобіль → VIN → Визначити автомобіль.
2. Record the actual source, returned fields and missing fields. Source-reported facts require review; ModelYear is not a factory production-date proof. Do not infer generation, engine/gearbox codes or exact modification from an expected model.
3. If NHTSA is partial, only the existing free fallback respecting robots may supplement it. Paid Vincario is not called. If access fails, report unavailable + manual fields; do not paste fixtures as live data.
4. Edit a nonessential test field, confirm, save in the test workspace, reload the card, verify core fields and vin_details attributes/source snapshot. Check duplicate VIN is blocked and offers the existing card. No need to create an extra donor in the working workspace.
5. Confirm no parts/stock/catalogue generation was created. Stop after VIN acceptance.

## Real specifications currently available

| Requested VIN | Actual external specifications received | Missing / reason |
|---|---|---|
| YV4L12RK6N1970668 | None verified | All requested specifications UNVERIFIED: CONNECT 403 before provider response |
| YV4A22PK2G1092943 | None verified | All requested specifications UNVERIFIED: CONNECT 403 before provider response |

Live decode, live persistence and actual staging URL remain UNVERIFIED until the authorized Console/browser sequence is completed. **Do not report this candidate as deployed or the VIN source as verified.**
