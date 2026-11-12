# Provider contract v1 — fixture only

Verified source context: read-only audit 2026-11-12. No LiqPay credentials or financial
API calls were used during Phase 1. Existing legacy routing is intentionally untouched.

`providers.PaymentAdapter` defines a verification boundary. `FixtureAdapter` accepts
in-process `ProviderEvent` only: provider=fixture, environment=test,
merchant=disposable-fixture, integer positive amount, UAH, stable event and transaction
IDs, status pending/success/failure. It is not cryptographic verification and is never
an HTTP endpoint. No production adapter exists. Invalid environment/sandbox/provider
events cannot create a settlement. Fixture entitlements cannot activate real services.

An adapter must validate original raw bytes/signature before producing trusted events.
Billing independently correlates immutable intent amount/currency/merchant/environment.
Transport event ID and financial transaction ID have different uniqueness scopes.
Unknown provider states must not be coerced to failure. Subscribed enrollment is not
proof of payment; result_url is never settlement evidence. Failed/pending late events
cannot undo success. Refund/reversal/chargeback require future explicit journal flows.

| Capability | Official documentation evidence | CarPot merchant status |
|---|---|---|
| Hosted one-time Checkout | documented | UNVERIFIED; not implemented here |
| Hosted recurring enrollment | documented | BLOCKED on merchant contract/sandbox tests |
| Provider retries | documentation describes 3 retries in 72h | exact lifecycle/identifiers UNVERIFIED |
| Cancel/change recurring | documented | acknowledgement and race behavior UNVERIFIED |
| Status lookup | documented | live reconciliation adapter absent |
| Full/partial refund | documented | funding, fees and permission UNVERIFIED |
| One-click/token charge | additional manager activation described | BLOCKED |
| Internal balance topups | not established by API existence | BLOCKED on legal/provider approval |
| Card/account payouts | application, agreement and bank activation required | BLOCKED; no payout implementation |
| One merchant, multiple own products/domains | technically routable | BLOCKED on merchant confirmation |

Official sources:
- https://www.liqpay.ua/doc/api/internet_acquiring/checkout
- https://www.liqpay.ua/doc/api/internet_acquiring/subscription
- https://www.liqpay.ua/doc/api/callback
- https://www.liqpay.ua/doc/api/information/status_payment
- https://www.liqpay.ua/doc/api/internet_acquiring/refund
- https://www.liqpay.ua/doc/api/transferring_to_card

BLOCKER: current explanatory text describes v7/SHA3-256, while examples on the same
pages still include v3/SHA-1. Legacy code uses v3/SHA-1 and hardcoded sandbox. Do not
claim compatibility or switch algorithms based only on mixed documentation. Obtain
merchant-specific confirmation and official vectors before implementing an adapter.

Required confirmation: supported protocol/signature, supported products/domains/legal
entity, hosted recurring consent, each renewal's unique transaction, retry timing,
cancellation finality, tariff changes, delayed callbacks, status/refund reports, wallet
topups, payout eligibility, fees, settlement and reconciliation exports.

Next LiqPay package: confirmed contract -> separate adapter -> recorded synthetic
contract fixtures -> raw signature and amount/currency/merchant checks -> sandbox
Checkout/status/refund tests -> reconciliation exceptions -> separately approved staging
acceptance. Start manual Checkout first; recurring is an independent gate. Keep legacy
callback URL and seller subscriptions on compatibility routing until separately migrated.
