# Price Reference Workspace — bounded follow-on to PR 586
Base: 00830087a6b6406d9106c402951d7af0a2d80c21. Separate branch, no changes to active CI or Railway.

- Inventory toolbar selects checked rows, filtered active stock, donor or all active stock. Cursor selection across pages, hard limit 5000 (no partial selection). Selection endpoint still owner-only; no migrations.
- Two phases: collect anonymous references; explicitly confirm writes. Default preserve existing prices, same condition/currency, unique group with >=3 prices. Exact preferred; similar requires opt-in. Average/minimum/maximum and -99..100% adjustment using integer cents. No automatic FX. Manual and single quick apply use existing authorized PATCH, token and UUID request key.
- Progress counts actual completed items; pause stops after in-flight request. Session storage persists scope, preview token, pending exact request and results. Reload requires explicit resume. No background work, no durable server queue, no atomic cross-part transaction. 5000 upper bound, sessionStorage capacity may limit job; storage failure pauses before write.
- Price updates use existing audit/idempotency path; no stock mutation. Source names and links absent from new UI.
- Live access remains OFF until documented approval; cannot claim real provider coverage. No new deployment/production changes. CI acceptance pending.

## Verification scope
- Unit policy tests are wired into npm prebuild (decimal arithmetic, comparable groups, opt-in similar, progress, single-row retry isolation).
- Backend regression covers reference revision, actual idempotent price write, stale-token rejection and unchanged stock fields; cursor selection tested.
- Existing sales-browser full release flow now includes real isolated API writes, synthetic anonymous reference observations, lost-response replay of one selected row, no unintended writes to other rows, explicit bulk apply and preservation of existing price at 1440 and 390 px.
- Current full integration outcome pending. This is a follow-on PR #587; PR #586 remains untouched. No real stock writes.

## Individual clarification UX
- Row/search action opens anonymous price dialog. Quick preview uses inline expandable panel, no additional modal. Groups separate conditions/currency; average/min/max for 3+ observations; selectable individual offers, including 1–2 observations clearly labeled as individual not average. Default only unique matching condition/currency cohort, exact preferred. User can adjust amount before explicit PATCH. Existing optimistic token/idempotency and recovery preserved. Manual editing remains possible without reference. Truncated data never offered for reference-based apply.
- Additional unit and browser regression tests cover individual selection, editable amount, unchanged price on lookup, explicit replacement and no changes to other stock/price rows. Pending CI. No live activation or Railway deployment.

## Final browser stabilization
Run 45870685521 integrated job 140084995551 failed after individual PATCH and correct DB assertions: sales-browser.mjs:156 could not find Close because the inventory refresh unmounted the row-owned dialog. Keep confirmed price in local panel; defer inventory refresh until explicit close/collapse or unmount. Both reference and manual editor use same deferred notification. Regression now asserts success panel and confirmed price remain visible, explicit close, then refreshed row; no skipped check or timeout change. CI pending. No finance feature work, no live activation or deploy.
