# Internal API and event contract v1

Status: DESIGN CONTRACT, not mounted HTTP routes. Implemented Python commands are
local fixture equivalents in `bot.billing.service.Billing`. No public auth integration
is claimed. An HTTP adapter is deliberately postponed until trusted principal/company
binding and service authentication exist. Do not serialize Actor permissions from clients.

Proposed namespace `/internal/billing/v1`:

| Operation | Scope | Local equivalent |
|---|---|---|
| GET /catalogue | versioned read | CATALOGUE / plan_versions |
| POST /quotes | billing.view + bound subject | catalogue.quote |
| POST /workspace-bindings | billing.manage + separately verified ownership | bind |
| POST /subscriptions | billing.manage + binding | subscribe |
| POST /invoices | billing.manage + subscription, Idempotency-Key | create_invoice |
| POST /invoices/{id}/issue | billing.manage | transition_invoice(open) |
| POST /invoices/{id}/void | billing.manage, no outstanding intent | transition_invoice(void) |
| GET /invoices/{id} | billing.view + account scope | invoice |
| POST /invoices/{id}/intents | billing.manage | create_intent (fixture only) |
| GET /subscriptions/{id}/entitlements | account/product/workspace scope | outbox full snapshot contract |

Common money fields: `amount_minor` integer, `currency=UAH`; never float. IDs are opaque.
Date fields are timezone-aware ISO-8601, stored UTC. Financial command idempotency scope
is account + key with immutable canonical request hash. Same key with different terms:
409. Forbidden/missing tenant object: 403 without foreign metadata. Validation: 422.
Feature disabled/provider unavailable: 503. No automatic retry for unknown money state.
These are future HTTP mappings of current typed exceptions, not running endpoints.

Binding input carries an opaque one-use evidence reference issued by a trusted verifier,
not a caller assertion of email/phone/workspace ownership. Internal delivery requires
authenticated service transport and issuer/audience authorization before real integration.
Consumer provisioned binding is checked independently from incoming account/workspace IDs.

## Webhook inbox

No fixture HTTP webhook. Future public provider adapter verifies raw message, normalizes
it, and invokes the transaction boundary. Event evidence is identified by
`(provider,event_id)` plus canonical payload hash. Transaction settlement uniqueness is
`(provider,transaction_id)` and invoice ID. Amount/currency/merchant/environment must
match original intent. Duplicate identical event is accepted; conflicting identity is
rejected and must enter future reconciliation/admin review. No PII/card payload persisted.

## Outbox: billing.entitlement.snapshot.v1

Envelope: schema_version=1, event_id, account_id, workspace_id, product, subscription_id,
monotonic version, sku, plan_version, limits {vehicle_capacity,employees}, paid_intervals
[{start,end}], environment=test, activates_real_services=false. Limits are capacity,
not monthly consumable credits. Paid intervals are complete, sorted and non-overlapping.

Consumer requires provisioned account/workspace/product/subscription binding. First apply
commits inbox and snapshot atomically. Same event/content is duplicate; same event/different
content or same aggregate version/different snapshot is conflict. Older versions are stale.
Consumers can skip versions because each event is a full snapshot. No distributed financial
transaction; consumer has no wallet/ledger authority. Replay never expands real access.

See `entitlement.schema.json` for machine-readable local fixture envelope. Real production
envelopes require a separately reviewed version/transport policy, not changing test flags.
