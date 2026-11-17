# Control Center checkpoint 004 — bounded financial reads

Date: 2026-11-15 Europe/Kyiv. Branch: feature/carpot-control-center-warehouse.
Base fdaef3c638765ca845692727f90c9f140395891b.
Verified application SHA 4e4a5f07e6f977d967b4b9d9277d929c61055adb.
PR not created: API Forbidden; code pushed. No live Billing configuration changed.

Implemented: explicit finance detail read after staff company scope + finance
permission. Support cannot receive amounts even with an erroneous finance flag.
Only existing verified binding/environment references are used. Billing remains
authority; no Finance DB credential is supplied to the BFF.

Minimal dependency outside Warehouse: bot/billing/staff_read.py, two registration
lines in api.py and two dedicated integration tests. Endpoint defaults OFF;
separate control-center peer and billing.staff.read transport, capability,
issuer/audience/environment/method/path/body/expiry/nonce/binding/workspace checks.
Shared peer keys rejected; existing global limiter reused. No customer membership
is synthesized. Receipt nonces are the only writes; financial queries SELECT-only.

Reads latest <=100 invoices/payments/reversals/reviews and latest canonical paid
intervals with explicit incomplete coverage. No totals inferred from the page;
legacy success/parts sales/trial/grace are not reported as confirmed revenue.
No MRR/churn/cash summaries without approved policy/complete source. Missing
peer/binding/Billing outage is unavailable, never zero; directory/notes survive.

Files: bot/billing/{api,staff_read}.py, tests/test_staff_read.py;
Warehouse control_center/{finance,api,projection}.py. No Finance migration.
No checkout/provider/profile/price/journal/settlement/referral/recurring mutation.

Local tests: 145 Billing PASS / 0 FAIL / 0 SKIP; includes two real disposable-DB
staff reader tests: signed scope, env, replay, other product denial, duplicated
callback -> one payment, and financial table counts unchanged after read.
CC suite 29 PASS covers scope/amount redaction/unavailability. Synthetic provider
evidence only; no real LiqPay request. A wider independent finance gate is added
in workflow commit 8bf83c45 (see final checkpoint for its completed outcome).
Runtime: live endpoints/flags/merchant state unknown; earlier Sandbox evidence
not mislabeled as a new runtime test. Next: UI checkpoint 005.
Rollback: new flags OFF, prior code, preserve all finance/customer/CRM histories.
