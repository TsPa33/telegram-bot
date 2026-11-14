# CarPot referral Sandbox pilot

Base: Billing Final UX #536. No schema change; schema 008/009 already contains the referral ledger and restricted grants.

## Scope
- Warehouse owner-only referral cabinet; exact stable code; explicit acceptance before first confirmed base settlement. No automatic attribution based on URL, email or phone.
- A link points to /settings?section=referrals&ref=CODE. The validated code survives the normal sign-in/register transition. Registration remains subject to existing Warehouse settings. An invited company first connects Billing, then explicitly confirms the invitation.
- 20% policy v1 with a 14-day hold is the existing test policy; production policy requires approval. The balance is ledger-derived; historical conversion count includes subsequently reversed first payments. Rewards list is limited to 100, totals are not.
- No production rewards, spending, payouts, new payment flows or automatic release worker. Existing internal release method can be exercised in disposable tests; due date is eligibility, not a promise of payout.
- Billing and Warehouse both have independent Sandbox-only flags; flags OFF by default. Do not enable production or recurring, wallet spending, delivery or reversals as part of this pilot.

## Rollout
1. Complete CI on the exact PR SHA, approve staging deployment.
2. Deploy Billing API and Warehouse API with flags OFF; same SHA, preserve existing start commands and credentials, no migrations.
3. Enable BILLING_REFERRALS_TEST_ENABLED=true and WAREHOUSE_REFERRALS_TEST_ENABLED=true only in warehouse-staging, then deploy Web. Existing warehouse dry_run and live payments OFF.
4. Use two isolated sandbox companies and explicit invitation before the invitee's first confirmed payment; verify one 200 UAH pending reward for Standard. Real LiqPay sandbox acceptance is distinct from the synthetic CI.
5. Rollback: disable both flags, restore previous Web/API/Billing SHAs; keep all finance history. Existing payments must continue to work.

Production policy, verified legacy account merge, real reward spending, release scheduling and payout are separate gates.
