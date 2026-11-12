# Validation evidence

Only disposable local PostgreSQL was used. Finance, Warehouse test suites, baseline
comparison and browser fixtures have separate databases. No staging/production data,
Railway variables, provider credentials, real callbacks, payments or deployments.

Commands:
- `python -m bot.billing.run_fixture_tests`: original 49 Phase 1 cases plus Phase 2
  void reissue, excess-payment evidence, calendar helper and persisted anchor regressions.
- Warehouse `pytest tests/test_entitlements_phase2.py`: signed two-DB binding/trial,
  capacity Standard/Premium, VIN/global ingress, last-slot race, archive/reserve/origin,
  returns after expiry, old-order completion without line inflation, temporal downgrade
  and add-on expiry, team concurrency/reactivation, trial race/deadline and transport scope.
- Full Warehouse `pytest tests` and independent failing-case comparison at untouched
  Phase 1 SHA. Do not interpret a focused green suite as full application acceptance.
- Frontend `node --test tests/*unit*.mjs`, `npm run build`.
- Authenticated `tests/billing-phase2-browser.mjs`: Chromium + WebKit, 320/390/430/1440,
  Midnight Gold and Forest Slate, actual API trial/last place/quote and retained deadline.
  Sixteen screenshots plus machine-readable report are in warehouse/docs/billing-phase2.

Local WebKit libraries were downloaded from official Debian repositories into the
workspace because this environment has no sudo/package helper. Playwright's host
preflight was skipped only after supplying the actual shared libraries in the local
browser bundle; successful browser launch and E2E are the evidence. CI installs native
browser dependencies normally. No TLS verification was disabled.

Exact final counts, known full-suite blockers and independently observed GitHub CI
status are recorded in the Draft PR acceptance section and validation-results.json.
