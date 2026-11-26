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
