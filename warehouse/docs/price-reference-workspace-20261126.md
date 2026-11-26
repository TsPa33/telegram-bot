# Price Reference Workspace — bounded follow-on to PR 586
Base: 00830087a6b6406d9106c402951d7af0a2d80c21. Separate branch, no changes to active CI or Railway.

- Inventory toolbar selects checked rows, filtered active stock, donor or all active stock. Cursor selection across pages, hard limit 5000 (no partial selection). Selection endpoint still owner-only; no migrations.
- Two phases: collect anonymous references; explicitly confirm writes. Default preserve existing prices, same condition/currency, unique group with >=3 prices. Exact preferred; similar requires opt-in. Average/minimum/maximum and -99..100% adjustment using integer cents. No automatic FX. Manual and single quick apply use existing authorized PATCH, token and UUID request key.
- Progress counts actual completed items; pause stops after in-flight request. Session storage persists scope, preview token, pending exact request and results. Reload requires explicit resume. No background work, no durable server queue, no atomic cross-part transaction. 5000 upper bound, sessionStorage capacity may limit job; storage failure pauses before write.
- Price updates use existing audit/idempotency path; no stock mutation. Source names and links absent from new UI.
- Live access remains OFF until documented approval; cannot claim real provider coverage. No new deployment/production changes. CI acceptance pending.
