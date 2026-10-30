# R8.4 — PartLine provider preparation (LIVE ACCESS BLOCKED)

Base `caf9f5cdb25bce07f05836a4cd8e6ae003114e68`, `feature/carpot-warehouse-mvp`, `/warehouse` only. This commit prepares a fail-closed provider boundary and a clearly synthetic XML test path through the existing Cloud Runner. **It does not implement or verify the official GetPrice wire contract. The main real-price acceptance criterion remains BLOCKED.** No push/deployment/staging/production mutation or live price lookup performed.

## Official API audit — facts and unavailable evidence

Requested documentation: <https://partline.com.ua/api/GetPrice>.

On 2026-10-30, an HTTPS documentation read using curl (`--proto '=https'`, 25-second timeout, 1 MiB cap, no redirect following) failed **before reaching the site**: `curl: (56) CONNECT tunnel failed, response 403`. The captured tunnel response was `HTTP/1.1 403 Forbidden`, `server: envoy`. This is the Codex network gateway response, **not a PartLine API rejection/authentication response**. No attempts were made to bypass the gateway, scrape another site or query real articles. An in-session request for documentation/XML examples and access terms was sent without asking for secrets; none was available at implementation time.

| Question | Actual evidence / status |
| --- | --- |
| Current GetPrice methods, path and request/response XML | UNVERIFIED. The supplied URL may describe an API; it is not assumed to be a callable price endpoint |
| Authentication, partner enrollment, credential shape | UNVERIFIED. No credential names, query tokens, auth headers or request body invented |
| Demo/test access | UNVERIFIED; not used |
| Automated use and third-party/commercial reuse permission | UNVERIFIED. Public documentation alone is not permission |
| API quotas, timeout, error codes and retry guidance | UNVERIFIED; our conservative local test limits are not represented as PartLine limits |
| Actual external API response received | **No** |
| Current actual offers/prices received | **No** |
| Official response fields verified | **None**. All field mappings below are an explicit CarPot synthetic test contract |
| Cloud worker provisioned/healthy | UNVERIFIED in this task; local independent worker CLI verified only |

A provider/partner agreement or approved demo method may be required, but this has not been established as fact. Before implementing an HTTP adapter, supply the current official contract (redacted examples including empty/error/auth responses), the authorized access channel, limits and terms allowing this intended data use. Do not send credentials through chat or commit them.

## Implemented / deliberately disabled

- Owner-only source status and one-article plus optional-manufacturer controls in the existing admin page.
- “Перевірити ціну через PartLine” is **always disabled** while the contract/access is unverified. `live_lookup()` fails closed even if arbitrary environment/client flags claim approval. No live job type, HTTP client, fallback to imported prices or credential-reading path is enabled.
- Separate expandable **“Локальний тест XML · синтетичні дані”** action creates `job_type=partline_fixture`, `source=partline_fixture` in the existing PostgreSQL queue. The button and every result explicitly say synthetic/not live.
- The synthetic fixture uses **our own** root `<carpot-partline-fixture version="carpot-partline-fixture-v1" synthetic="true">`, not an invented `<GetPrice>` implementation. An unknown official-looking XML response fails closed until its real contract is reviewed.
- Reuses R8.2 worker, leases, heartbeat, account scoping, CSRF/session/allowlist, append-only events, retries, history and R8.3 durable checksummed artifacts. No Redis/Celery/new queue/new worker service.
- Supports source article, optional returned manufacturer, original name, Decimal price, original currency, nullable test quantity and test availability. No catalogue normalization, Aleto extraction, canonical engine or financial/stock algorithms changed.
- UAH/USD (and EUR in the synthetic contract) remain separate. Invalid price/currency is an error, never a guessed currency or conversion.
- Exact repeated test observations deduplicate; different currency/price observations remain distinct. Unknown article/manufacturer returns **fixture_empty**, not a claim about actual PartLine stock or article existence. No old/imported/live fallback.

## Persisted results and price boundaries

A bounded JSON result artifact and summary contain:

```json
{
  "source": "partline",
  "source_type": "new_parts",
  "mode": "fixture",
  "synthetic": true,
  "live": false,
  "observed_at": null,
  "external_requests": 0,
  "request_status": "fixture_only",
  "request_completed": false,
  "recommendation_eligible": false,
  "committed": false,
  "offers": []
}
```

Each test offer contains `source=partline`, `source_type=new_parts`, `source_article`, `manufacturer`, `original_name`, Decimal-string `price`, `currency`, nullable `quantity`, `availability`, `observed_at=null`, `request_status=fixture_only`, `synthetic=true`, `oem_confirmed=false` and `vehicle_compatibility=unverified`. The fixture demonstrates two currency observations and one exact duplicate for `SYN-PL-001` / `Synthetic Brand`. These are not real products or prices.

**No external query occurred**, so there is no factual external observation/request date: `observed_at` remains null. Job start/finish timestamps describe execution of the synthetic test only. The UI says “Фактична дата зовнішнього запиту: немає”. A future verified HTTP adapter must stamp the real attempt/response observation time rather than a fixture date, file mtime or old catalogue observation.

Records live only in job summaries and private `import_job_artifacts` result JSON, with input fixture hash + output SHA-256. No offer/price is inserted into global/Aleto catalogue tables or seller-price/stock/finance tables. **PartLine results cannot use the Aleto import hand-off endpoint** (`409`): the guard is on the server, not just a hidden button. Thus new-part prices do not silently influence used-part recommendations. No OEM claim or vehicle fitment is inferred from an aftermarket number or successful lookup.

R8.3 storage remains durable PostgreSQL bounded BYTEA; this adapter limits input/output to **128 KiB**, below its 1 MiB database cap. No dependence on API/worker temporary disk after restart. Versioned synthetic XML is copied with the app in the existing worker Dockerfile. No new storage service, dependency or credential is required for the local synthetic subset.

## API / lifecycle / strict test limits

- `GET /api/v1/admin/import-jobs/partline`: owner-only readiness/capability report. `status=blocked`, `live_enabled=false`, `contract_verified=false`; reasons include unavailable docs/auth/reuse/demo/cloud validation. No secrets or environment values returned.
- Existing `POST /api/v1/admin/import-jobs`: `{job_type:"partline_fixture", article:"SYN-PL-001", manufacturer:"Synthetic Brand", request_key:"<UUID>"}`. Manufacturer optional. One string article only; no arrays, arbitrary URL/code/key/account/model/mode/live flags.
- Existing list/detail/events/cancel/retry/result routes are reused and scoped to the server-derived actor/account. Download is `partline-SYNTHETIC-result.json`, private/no-store/nosniff with `X-Content-SHA256`; checksum checked before delivery.
- Same creation key/body replays the same durable job. Changed key/body conflict and active-context duplicate rules remain. Replay occurs before quotas and does not consume another job. One immutable result per job; a completed job cannot be retried. New explicit runs have separate history and never create catalogue offers or stock.
- One article/job; **zero external requests**. Five new PartLine test jobs/account/hour, twenty globally/hour persisted in PostgreSQL. A provider-specific advisory submit lock serializes global quota checks across accounts; actor locks serialize account commands. Original overall <=2 active/account and <=20 new jobs/15min still apply.
- One executing PartLine test/database via provider advisory transaction lock, within the existing two global worker slots. Busy attempts fail explicitly, no hidden API retry or spin. Maximum three execution attempts and three explicit retries/job remain inherited; job creation quotas count new intents, not credential/network retries (there are no network requests).
- Strict parsing/execution checkpoints use a 10-second local processing budget, 128 KiB input/output, at most 100 test offers and XML depth <=8. No meaningful live HTTP timeout/rate guarantee is claimed for a transport that has not been authorized/implemented.
- Per-job execution advisory fence + 30s lease/5s heartbeat + final token/state/actor/deadline check remain. Cancel/SIGTERM/SIGKILL roll back speculative artifact and completion together. Recovery restarts the immutable small fixture; no unfinished external request is silently repeated.
- Credentialed HTTP retry semantics, especially timeout-after-send, must be specified against the approved API contract before any live code is added. No batch interface in this commit.

## XML / security

XML is UTF-8 only, size-bounded; DTD and ENTITY declarations are rejected before standard-library parsing. No external entity resolver, XInclude, stylesheet or XML-triggered request. Unknown roots/namespaces/schema/fields/depth, invalid money/currency/quantity and malformed XML fail closed. There is no XXE fetch path. Error messages are allowlisted codes/messages, not raw XML, secret-bearing bodies or exception URLs.

`validate_reference_url` permits only the exact HTTPS documentation identifier on `partline.com.ua`, without query, credentials, explicit port or fragment. **It does not send requests or prove provider access**. Because live HTTP is absent, clients cannot exploit redirects/SSRF through this source. Before a real HTTP transport is added, exact endpoint/method, TLS, DNS/IP revalidation, redirects OFF, streaming response caps, wall-clock timeouts, auth redaction and provider-approved retry/rate policy must be implemented and tested with approved access. This work is not falsely represented as completed here.

No live credential configuration exists yet because the authentication contract is unknown. Future reviewed credentials must be server-side private Railway Variables/references only, never job parameters, URLs, UI, git, artifacts or logs. Tests use dummy strings only to prove environment flags cannot activate live mode. No Variables changed.

## Migration / compatibility / deployment boundary

New single head **`e4b93a2d715c`**, parent **`d3a82f1c904b`**. Only widens `ck_import_runner_type` to permit the explicit synthetic PartLine source/type pair; no new table/column, backfill or warehouse/financial schema change. Existing R8.3 rows/artifacts and old file jobs remain valid. Downgrade refuses while PartLine test history exists. API still owns serialized startup migration; no manual/staging migration was run.

Frontend known-head checks add the new head while retaining earlier known revisions. Old heads are not accepted arbitrarily. Current-head test expectations were updated; historical revision-chain assertions remain. API/worker Dockerfiles, requirements and commands are unchanged; no package update. No Railway service or deployment created. A later release still needs normal migration/API/Web/worker validation, independently of the separate PartLine contract/access blocker.

## Verification

Only dedicated loopback `warehouse_r84_*_test` synthetic databases and accounts were used. Tests include XML/Decimal/currency/unknown articles/empty result, malicious XML/entities/URL references, size limits, simulated timeout/rejection/auth/redirect responses, checksummed artifacts, no import hand-off, cancel/rollback/retry, missing storage/changed fixture, provider lock/quota, actual child-process SIGKILL/recovery, RBAC/CSRF/cross-account isolation, R8.3 Aleto offline, existing file preview, orders/sales and populated migration/data preservation.

**These are tests of our explicit synthetic envelope and error classification, not actual PartLine HTTP acceptance or parser compatibility.** No actual remote trial was allowed/possible because demo access is unverified. No synthetic test is reported as a real market quote.

- Backend affected regression: **184 passed** (PartLine synthetic adapter, Aleto offline, durable runner, admin/file jobs, catalogue v2, orders/sales and staging checks).
- Frontend build **PASS**; full frontend units **460 passed**, including fixture-command recovery and rejection of live/URL/credential/account overrides.
- PartLine preparation browser QA **PASS at 1440/1280/1000/900/768/390/375px**, using synthetic DB and real independent worker. Real worker execution/browser-close checks at 1440/390/375; the other widths reuse completed fixture results for responsive/read-only QA. Mobile cancel/retry at 390, unknown article fixture at 375, disabled live button and no external requests/JS errors/horizontal overflow at every width.
- Aleto R8.3 offline browser regression **PASS at all seven widths**, including separate worker, queued reload, cancel/retry, explicit file hand-off and no apply.
- Source API/official contract/actual remote prices: **UNVERIFIED / BLOCKED**, not part of these synthetic PASS claims.

Evidence: `/tmp/r84-backend.log`, `/tmp/r84-build.log`, `/tmp/r84-unit-final.log`, `/tmp/r84-browser-final.log`, `/tmp/r84-aleto-browser.log`. Nonblocking warnings: existing Starlette/httpx deprecation and Vite chunk-size advisory; no related dependency/refactor added. Screenshots/results: `/workspace/scratch/r84` (local synthetic only). [Desktop](desktop.png), [Mobile](mobile.png), [Changed files](changed-files.md).

## Release blockers / needed evidence

1. Current official GetPrice documentation and request/response/error examples.
2. Confirmed authorized test/partner access, authentication contract and permission for this third-party data use.
3. Approved provider limits/retry rules and real HTTPS transport/security review.
4. Credential provisioning through reviewed private Variables, separately authorized; no secrets through chat.
5. Actual single-article trial using an expressly permitted test mode, then verify the returned factual fields/prices/time without changing seller stock/finance.
6. Cloud worker provision/runtime and end-to-end provider verification remain unverified here. No live button until both access and the runner are verified.

**Status: SAFE PREPARATION COMPLETE; REAL MARKET PROVIDER BLOCKED / UNVERIFIED.** No R8.5, import rewrite, canonical change or FileDbTree work started.
