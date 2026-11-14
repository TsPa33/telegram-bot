# CarPot Checkpoint 010 — Phase 3B

Date: 2026-11-14 Europe/Kyiv. Branch `feature/carpot-global-liqpay`.
Verified original base: `b45d3789f4ec7da267da60779cad489866dbb4b6`; package base `c8934d5`.
Head: commit containing this checkpoint (`git log -1 --format=%H -- docs/billing/checkpoints/CarPot_Checkpoint_010_Phase3B.md`). Draft PR: https://github.com/TsPa33/telegram-bot/pull/534.

Extended the existing Settings → WorkspaceBilling panel: current limits and subscription, Standard/Premium, trial, prorated add-ons, invoice summary/detail/void, official hosted POST, payment history and server status polling. No separate navigation or card collection. Owner-only financial controls. Existing OperationProgress is reused. Scoped persisted purchase commands and canonical immutable orders recover lost responses. Browser return cannot activate rights; paid status still requires a synchronized server entitlement before the success message. Future periods and refunded payments have distinct honest messages. Previous local pilot remains behind flags OFF.

Files: `warehouse/frontend/src/{WorkspaceBilling,billingCabinet,WorkshopDialogs,smartSearch,teamReadiness}.tsx/ts`, billing CSS, pure unit tests and `billing-global-browser.mjs`; two explicit disposable-only browser drivers; existing Warehouse billing API returns workspace scope. Existing nginx CSP permits only the official LiqPay form destination. Payment status exposes immutable effective dates/reversal totals. Delivery acknowledgement of a newer full snapshot supersedes older outbox versions so obsolete rights cannot block activation indefinitely. No additional migration in this package; Warehouse head remains `b23c45d67e89` and is explicitly recognized by readiness guards.

Verification: frontend 636 tests passed and production build passed before the final scope/error-message correction; repeated verification is recorded at the final gate. Synthetic real-browser matrix covers Chromium/WebKit, 320/390/430/1440 and Light/Onyx/Midnight Gold/Forest Slate. It uses separate real disposable Finance/Warehouse databases, real authenticated APIs, an intercepted synthetic hosted page and signed synthetic evidence. It includes invoice/checkout response loss, exact order recovery, pending return, one settlement, entitlement activation, overflow and script-error checks. This is not a genuine LiqPay Sandbox test. Full matrix artifacts and independent CI are attached at Checkpoint 014; no staging/production UI has been changed.

CI: https://github.com/TsPa33/telegram-bot/pull/534/checks (final code CI pending the package series).
Staging/production: unchanged; no deployment, variables, merchant secrets or paid resources touched.
Blockers: actual merchant Sandbox profile/credentials and approved Billing service deployment. Production checkout OFF.
Next: Phase 3C product routing, legacy compatibility, server-hosted Telegram payment links and projections.
Resume: use this branch and checkpoints 008–010; run the browser drivers only with WAREHOUSE_E2E=1 and explicit loopback *_test databases. Never expose fixture helper routes in an operational image.
Rollback: disable global flags and roll back code; preserve invoices, settlement, journal, reversals and snapshots. Forward-only database corrections.
