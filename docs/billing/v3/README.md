# CarPot Billing Phase 3A.1 — isolated LiqPay Checkout candidate

Base: verified Phase 2.2 merge `51b87f5fae55e14b44ce6ab1e6706aa54153a5ba` (PR #532).
Scope: sandbox protocol codec and durable local order/callback evidence. Not live
Checkout, not a deployment, and not production billing activation.

## Implemented

- Candidate v7 / SHA3-256 signature over the original base64 data; compare the
  signature in constant time before decoding JSON. No silent v3/SHA-1 fallback.
- Fixed one-time `pay` Checkout POST form and signed `status` request parameters.
  The codec does not send either request. Prices are integer UAH minor units and
  come from an existing immutable issued invoice, never a frontend amount.
- Explicit sandbox-only key prefixes, HTTPS return/callback configuration,
  namespaced opaque order IDs; no production credential discovery.
- Correlate merchant, version, action, order ID, currency, amount, and successful
  payment identity. Reject malformed/duplicate-field JSON and invalid signatures.
- Local-only immutable order, callback-evidence, and provider payment-ID records.
  One order per invoice, owner permissions and tenant scope; transaction-safe
  repeated checkout/callback, late events and duplicate provider payment IDs.
- `success` and `sandbox` are **test success** only. Pending/failure are not
  settlement, unknown/reversal/recurring states require review. A repeated or
  different payment ID never creates a second charge or grant here.
- No calls to the legacy LiqPay handler; no live payment, journal posting,
  entitlement publication, card collection, wallet, recurring or refund flow.
  All existing fixture settlement tests remain independent.

## Verification and operation

Synthetic data and keys only, including an independently generated OpenSSL
SHA3-256 signature vector. Run from the repository root:

```sh
python -m bot.billing.run_fixture_tests
```

The runner provisions disposable loopback PostgreSQL databases. The new migration
is explicit via `migrate_sandbox(db)` and uses the existing local-only Database
class; it is not called at Warehouse startup. No Railway variables or databases
are changed. The callback evidence records only necessary normalized fields and
the digest, not arbitrary raw callback payloads containing payer details.

Official contract references, checked 2026-11-14:

- https://www.liqpay.ua/doc/api/internet_acquiring/checkout
- https://www.liqpay.ua/doc/api/callback
- https://www.liqpay.ua/doc/api/information/status_payment
- https://www.liqpay.ua/en/doc/api/testing

The documentation prose identifies v7 and SHA3-256, while legacy code/examples
still use v3/SHA-1. This package is a candidate for the modern contract, not
merchant-specific confirmation or evidence of an actual LiqPay request. No
merchant keys were obtained or tested.

## Remaining release gates

1. Verify merchant-supported protocol and real sandbox Checkout/status/callback
   envelopes with LiqPay-issued sandbox credentials. Keep secrets in authorized
   server-side secret storage, never in code, PRs, logs or browser.
2. Approve operational finance database and deployment boundary; migrate the
   additive schema and separate sandbox/live order namespaces safely. Add the
   authenticated HTTP checkout/status boundary and a bounded raw callback parser,
   provider status polling/reconciliation and durable verified evidence.
3. Implement canonical financial settlement and entitlement delivery from
   verified **live** payment only (existing foundation remains fixture-only).
   Prove invoice, journal, outbox and entitlement consistency and replay safety;
   no activation from browser result_url or sandbox status.
4. Implement server-issued add-on invoices/proration and integrate the Warehouse
   billing cabinet with manual checkout for base plans and packs. Current local
   checkout accepts existing open invoices; no new add-on purchase or UI yet.
5. Separately approve sandbox rollout and merchant acceptance. Live payments,
   recurring consent/renewal, refunds, wallets and payouts require their own gates.

Rollback of this package: leave it disconnected and preserve the local evidence;
never delete financial history or revert a production migration.
