# CarPot individual market reference: independent second source

## Real observations (2026-11-26 UTC)
- Existing staging SHA 8d6d7b0866647a5d0acd44b98b1c899186731583: Aleto request logs showed source_not_found at product phase, plus expected cooldowns. No source-access bypass attempted.
- PartLine public example HTTPS request did not return the documented XML. Integration remains disabled; diagnostic was deleted. No credentials or returned implementation content retained here.
- AutoPalma read-only, temporary Railway probe (no DB, no domain, deleted): robots.txt HTTP 200 with single wildcard agent, forbidden /search and /price paths, allowed fixed public product path /daf/1686587. Product HTTP 200. JSON-LD Product with brand DAF, sku 1686587, exact product URL, Offer price 1174 UAH and InStock. This is one control item, not proof of coverage or fitment for the user's reported part.
- The product page contained analog rows; they are not used as exact matches.
- No paid API or new credential used.

## Implementation
- Individual lookup only, original staging gate plus separate WAREHOUSE_MARKET_AUTOPALMA_ENABLED=true opt-in. One Aleto product request, at most one AutoPalma fallback on 404/no cards/no comparable; no fallback on access/robots denial or quota. Same existing global per-click cooldown and budget, 24h in-process bounded cache; source rules checked.
- Brand + normalized OEM product path, fixed hosts, TLS pinning, no redirects or arbitrary URL input; parse only a matching JSON-LD single Offer; no aggregate, cross-reference, guessed prices or condition. Source condition unknown unless explicitly supplied. Display individual price and validated source link, not average. No stock or schema changes.
- Existing UI and permissions, bulk remains stored only. New tests cover the observed DAF shape, unsafe URLs, brand/OEM mismatch, cache, robots and access denial. Production remains disabled. Source terms and wider coverage require review before production.
- Runtime acceptance pending: CI, then staging deploy and authenticated individual click for real returned offer. No claim that any particular DAF part will be priced.
