# CarPot Checkpoint 012 — Phase 4

2026-11-14 Europe/Kyiv. Branch `feature/carpot-global-liqpay`; original base `b45d3789f4ec7da267da60779cad489866dbb4b6`; package base `165a066`. Head: containing commit (`git log -1 --format=%H -- docs/billing/checkpoints/CarPot_Checkpoint_012_Phase4.md`). Draft PR https://github.com/TsPa33/telegram-bot/pull/534.

Implemented a separate candidate recurring lifecycle, disabled by default. Immutable versioned explicit consent and enrollment identity; provider subscription identity; next-payment date; one canonical invoice/order per calendar cycle; immutable collection ownership prevents manual/recurring double collection; failure metadata delegates retries to the provider without launching parallel automatic charges. Paid access/grace still use existing entitlement intervals. Changing plan requires cancellation/confirmation of the old provider mandate and new consent. Enrollment `subscribed` never creates a settlement or rights. Each confirmed cycle crosses the same original payment verifier and atomic settlement boundary, with additional provider-subscription correlation.

Cancellation is a durable request available even after rollout flags are disabled. UI reports pending provider confirmation honestly. Signed candidate unsubscribe confirmation changes only auto-renewal, never deletes paid intervals. The cancellation form/command can be prepared after explicit capability confirmation; no autonomous worker sends it or charges a card.

Files: `bot/billing/recurring.py`, additive migration 007, API/Payments/GlobalBilling integration and `test_recurring.py`; existing Warehouse `/billing/cancel-renewal` gateway and WorkspaceBilling controls. Schema readiness advances to 007. No duplicate subscription state machine in Warehouse.

Verification: synthetic signed enrollment→cycle→decline→verified retry→cancel request→unsubscribe scenario PASS, including idempotency, wrong provider identity, manual double-collection prevention and preservation of two paid settlements/outbox versions. Complete financial suite including subsequent sandbox wallet work: 139 PASS/0 FAIL. Final independent CI: Checkpoint 014 / https://github.com/TsPa33/telegram-bot/pull/534/checks.

External blocker: real merchant recurring capability and exact enrollment/cycle/cancellation contract. In particular, the candidate profile requires a separately correlated invoice order for every provider cycle and a provider subscription identity; this is NOT asserted to match an untested merchant account. Provider date/timezone/retries/cancellation acknowledgements must be verified with genuine Sandbox. Until then `BILLING_RECURRING_ENABLED=false` and `BILLING_RECURRING_CONTRACT_CONFIRMED=false`; the cabinet does not offer enrollment. Production recurring is not ready and no real enrollment/charge/cancel was attempted.

Staging/production and Railway unchanged. Next: test-only wallet/referral ledger and final integrated regression.
Resume: checkpoints 008–012; explicit migrator applies 007; run `test_recurring.py` on disposable loopback databases. Review the contract acceptance checklist before enabling any provider network operation.
Rollback: flags OFF, retain immutable consent/cycles/financial records, code rollback; outstanding provider cancellations require reconciliation, never falsely mark them canceled. Forward-only corrections.
