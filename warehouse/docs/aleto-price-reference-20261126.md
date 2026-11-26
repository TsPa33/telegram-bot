# CarPot Aleto price reference — candidate

Base: 810a767a69c4633983f0a51412ee92abf3f4daa6, Warehouse universal intake branch. Separate draft; no deployment or database changes.

- Reuse POST /api/v1/parts/{id}/market-refresh and current RBAC, tenant scoping, CSRF, matching and 90-day age rules.
- Explicit per-part button in stock, search desktop/mobile, and donor board for existing stock cards. Plan-only rows without a unique stock card remain out of scope.
- Arithmetic mean, range and sample count use complete deduplicated matched Aleto observations, not the ten display examples. Exact/similar, condition and currencies are separate. Fewer than three observations, truncated inputs, stale and conflicting offers cannot yield a mean.
- No seller price, OEM, stock, finance, source database or migration changes. Existing bulk pricing policy untouched.
- Only imported observations; live access is not implemented or claimed. Approved source API/feed/access and contract remain outstanding.
- Acceptance: targeted unit/integration and frontend build/browser QA on CI, then isolated staging read-only acceptance. No production/main merge.

## Customer anonymity follow-up

- Explicit POST /parts/{id}/market-reference allowlist returns only numerical statistics, condition, match quality, observation timestamps, and anonymous examples.
- Stock/search/donor and part-card action share the same neutral UI. No source URLs or third-party articles are rendered in the new dialog. Existing market-price card links removed; legacy reference display relabelled.
- Existing internal/legacy APIs and administrator integration tooling remain; this is not a global data-loss or API access redesign.
- Imported price tables do not establish current availability. Treat results as historical observations, not confirmed in-stock offers; live access and redistribution rights remain release gates.

## Live provider candidate — bounded package

- Default OFF; requires WAREHOUSE_MARKET_LIVE_ENABLED=true and nonempty WAREHOUSE_MARKET_ACCESS_APPROVAL after documented source authorization. No variable changes in Railway. HTTP accessibility is not permission.
- Exact OEM route only; Toyota formatting verified. Missing OEM/unsupported page/failure/robots restriction falls back to saved observations; no arbitrary search endpoints, pagination, or crawling. No compatibility guarantee and no coverage claim for all makes.
- Fixed host, public-IP pinning, verified TLS, no redirects/proxies, bounded response and timeout. System DNS resolver timeout remains OS-managed. Unknown availability is kept separate; unavailable/expected excluded. Match by OEM, model, functional prefix, position, assembly, technical signature, condition and currency; at least three distinct cards per group for mean.
- Bounded in-process 24h cache (128 public pages); no tenant identifiers or VIN sent, no new DB/schema. Cache resets on process restart and is not shared across replicas. One concurrent fetch per process and 3s cooldown. No background calls.
- New customer response carries only anonymous numerical data and status. The older local API remains for compatibility; administrator provenance stays internal. Separate merge review required against the currently deployed Master Parts Catalogue branch. CI and end-to-end live acceptance required before activation.

## Integration base

Master Parts Catalogue integration base: 761573af6b6b698d65c28dca6ebaa370ce6d8814. Compared both descendants of 810a767a69c4633983f0a51412ee92abf3f4daa6; zero changed-path overlap before integration. Merged the master branch snapshot into the draft feature branch only; master branch, live deployments and all databases unchanged by this action. Both stored and live customer responses use an explicit anonymous DTO. Final combined CI must pass before staging acceptance; the live provider remains disabled until access approval is documented.

## Mobile integrated-browser stabilization

Release Gate 45855399582 attempts 1 and 2: desktop 1440 PASS, mobile 390 failed at sales-browser.mjs:48 opening stock submenu after checkout/reload. The log showed the button resolved but became unstable then invisible. Code inspection identified native popover auto-close on captured window scroll and search-field focus retention as plausible contributors; exact runtime event ordering was not instrumented. Fix: stable mobile bottom-anchored viewport-constrained popover, no dismissal on incidental background scroll, visualViewport resize tracking, focus restoration without scroll, exclude action buttons from search focus suppression. Native light dismissal and keyboard Escape remain. Regression covers search focus, scrolling and all original real stock/checkout assertions; no timeout increase, no forced click, no test skip. Final CI required.
