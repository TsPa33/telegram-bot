# R5.1 — Live source gate blocked; imported fallback retained

Base: `ac92f23d915c06302f31f025d2495a9add98fe8b` on `feature/carpot-warehouse-mvp`. Local-only changes under `/warehouse`.

## 1. Implemented

- Re-audited R5: tenant-local v1 Aleto offers/prices and global v2 immutable observations already exist. R5 uses Stage 3C `price_guidance`, not a parallel matching/pricing system. Existing OEM normalization, verified canonical mapping, side/model/year/condition/configuration checks, conservative uncertain examples and separate UAH/USD cohorts are retained.
- Additive `result_source` on existing `POST /api/v1/parts/{id}/market-refresh`: `imported` when allowlisted imported offer evidence is returned, otherwise `unavailable`.
- Existing `mode`, `status`, `checked_at`, `observed_at`, `offer_count`, `guidance`, `source_status`, `fresh_data_fetched`, `live_refresh_available`, `cached` and other R5 fields stay compatible. `source_status=source_unavailable` refers to inability to obtain live data; it is distinct from usable imported evidence.
- Card button renamed to **«Перевірити ринкові ціни»**. Short imported-only label remains visible. Technical explanation/search phrase/manual-import link are inside “Деталі перевірки”. A direct Aleto manual-check link remains visible outside it.
- The existing `market.check` permission, CSRF and session authorization remain enforced on the server; workspace is server-derived. SellerPriceEditor remains independent.

## 2. Source permission / access review

**Live access is NOT confirmed.** On 2026-10-30, standard HTTPS requests to `https://aleto.ua/robots.txt` and the homepage failed with `Tunnel connection failed: 403 Forbidden` at this execution environment's outbound proxy. No proxy override, alternate User-Agent, alternate hostname or alternate search route was attempted. This is not a claimed Aleto HTTP response or a finding that its terms forbid all access.

The user supplies that `/search/`, `/search-adv/` and their Ukrainian equivalents are disallowed by robots. They were **not requested**. No sitemap traversal, catalogue crawl or source extraction was run. Absence of a robots prohibition would not establish permission anyway.

An official API, permitted public-page integration, approved export agreement or owner-provided provider access agreement could not be independently verified. Their nonexistence is not claimed. No current Aleto prices were received. Manual permitted-export import remains the existing separately authorized platform-owner workflow, not something this endpoint triggers.

## 3. Actual live refresh

**BLOCKED / NOT IMPLEMENTED.** The existing imported-only implementation remains active; no mocked response is presented as successful live integration.

`result_source` reserves the semantic vocabulary `live`, `cached`, `imported`, `unavailable`; this build emits only the last two. It never returns `live` or `cached`. `fresh_data_fetched=false`, `live_refresh_available=false`, `cached=false` remain explicit. A current `checked_at` is only the time the local catalogue was read; it never replaces an offer's actual `observed_at`. Old historical observations remain excluded from recommendations.

No external HTTP client, background refresh, source-search URL generation, feature flag to enable collection, persistent market cache or new observation writer was added. Therefore no network operation occurs inside a database transaction. Repeated/concurrent reads cannot duplicate an observation or write a price. Prior observations survive errors unchanged. Existing local query bounds and 5-second statement timeout remain in R5.

A future live implementation requires a verified permitted access method plus the still-unimplemented live-specific SSRF/DNS/redirect checks, source timeouts/size bounds, server quotas/concurrency control, context-aware cooldown, restart-safe durable execution and immutable/idempotent observation insertion. No claim is made that current presentation-link validation alone supplies a safe HTTP fetching client. An approved sitemap could supply addresses only, never permission or compatibility evidence.

## 4. Models and data provenance

No additional models or live model coverage were introduced. Existing imported Volvo XC40/XC60/XC90 coverage remains subject to actual imported data, published canonical mapping and verified configuration. Other already imported catalogue models retain their existing Stage 3C behavior; no new compatibility is inferred.

Local tests use synthetic catalogue fixtures, including XC40. Real Volvo B, real donor fitment and fresh source results were **not** retested or claimed. All prices returned here are imported observations; there are zero newly fetched source observations. The offer-rendering JSON fixture is explicitly synthetic, not a source capture.

## 5. API, schema and data safety

Only the existing POST response is extended; there is no new route or migration. Alembic remains at `b7e14d90c2f6`. No stock/finance model changes, backfill, catalogue re-import or canonical publication. No modifications to `selling_price`, seller `currency`, quantities, reserves, historical prices, sales, orders, financial records or audit. Backend tests compare table contents and disable external socket creation during the check.

## 6. Verification

- 14 targeted PostgreSQL tests passed (`test_market_check.py`), including imported/unavailable provenance, allowed evidence and distinct dual-currency ad count, old observation exclusion, context invalidation, retry/concurrent read immutability, RBAC/CSRF, tenant scope and untrusted URL/body rejection.
- Full frontend unit suite: 447 passed. TypeScript/Vite build passed.
- Updated R5 browser suite: 1440/1280/1000/900/768/390/375px passed. Actual local imported-only API, loading/disabled button, collapsed technical details, manual link, no matches, original dates, synthetic historical-offer display, error/retry, preserved Part values, no JS errors or horizontal overflow. Includes read-only R3 center and R4 composer navigation; no orders are saved or sold.
- R1 browser regression: 1440/1280/900/768/390/375px passed.
- Matching/atomic-order algorithms are unchanged. Their prior R5 combined 72-test PostgreSQL result is documented in `../r5-aleto-refresh/README.md`; it was not misreported as a new full run for this metadata/UI change.
- Live success, cached live result, live source timeout, fresh parsing, robots-aware live acquisition and live-worker restart tests: **NOT IMPLEMENTED / NOT VERIFIED**, because the source gate failed. Fixture tests never load Aleto. No claim of live readiness.

Screenshots use synthetic local data:

- [Desktop](desktop.png)
- [iPhone](mobile.png)

Logs: `/tmp/r51-build.log`, `/tmp/r51-backend.log`, `/tmp/r51-unit.log`, `/tmp/r51-browser.log`, `/tmp/r51-reg-r1.log`. Browser evidence remains in `/workspace/scratch/r5`.

## 7. Local result / release limits

One local commit is created only after checks pass; its SHA is supplied in the final response. Worktree must be clean. No push, deployment, staging migration, production access or source collection occurs in this task.

**Live integration remains blocked**, with R5 available as an honest imported-catalogue fallback. To unblock, supply a verifiable official API/approved data-access method or permitted export with provenance. A usable network connection alone, or robots allowing a page, is insufficient authorization.
