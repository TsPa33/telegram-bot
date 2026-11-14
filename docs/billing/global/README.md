# CarPot Global Billing — implementation and operating contract

Branch `feature/carpot-global-liqpay`, verified source #533 `b45d3789f4ec7da267da60779cad489866dbb4b6`.
Draft [PR #534](https://github.com/TsPa33/telegram-bot/pull/534). Checkpoints [008](../checkpoints/CarPot_Checkpoint_008_Phase3A2.md)–[014](../checkpoints/CarPot_Checkpoint_014_Phase6.md) describe the package sequence.

## Boundaries and current readiness

The existing `bot/billing` accounts, catalogue, subscriptions, invoices, intents, inbox, settlements, balanced journal, outbox and reconciliation tables remain canonical. `GlobalBilling` orchestrates those tables; `Payments` accepts a separately verified LiqPay charge and calls the same atomic posting function as the original foundation. No LiqPay message is converted into a fixture event. `Database` remains disposable-only. `OperationalDatabase` is separate, environment-pinned, explicitly configured, and does not read `DATABASE_URL`.

Warehouse and Telegram hold only product projections and canonical binding/order references. Warehouse keeps its existing entitlement state, quota, trial, grace and donor policies. A return URL, browser state, legacy `success`, enrollment `subscribed`, or wallet topup cannot create canonical service access. A signed full snapshot is monotonic, tenant/environment scoped and acknowledged after the consumer transaction commits. A newer committed full snapshot supersedes older outbox deliveries, including reversals.

| Environment | State |
|---|---|
| Local | Implemented; disposable PostgreSQL, synthetic verification and real-browser acceptance. Exact test results at Checkpoint 014. |
| Genuine LiqPay Sandbox | Not accepted: no merchant-specific credentials/contract or genuine provider request verified in this task. Synthetic evidence is explicitly labeled. |
| Railway staging | Configuration prepared; no new service, database, migration, deployment or variable change performed. Existing Warehouse/Catalogue staging unchanged. |
| Production | Payments, recurring, wallet and payouts not released. Production requires merchant confirmation plus explicit live enable; recurring has a separate capability gate; wallet mutation rejects production unconditionally. |

## Official contract sources and acceptance blockers

Reviewed official pages on 2026-11-14:

- [Checkout](https://www.liqpay.ua/doc/api/internet_acquiring/checkout)
- [Callback](https://www.liqpay.ua/doc/api/callback)
- [Payment status](https://www.liqpay.ua/doc/api/information/status_payment)
- [Subscription](https://www.liqpay.ua/doc/api/internet_acquiring/subscription)
- [Refund](https://www.liqpay.ua/doc/api/internet_acquiring/refund)
- [Testing](https://www.liqpay.ua/en/doc/api/testing)

The documentation mixes modern v7/SHA3-256 prose and legacy v3/SHA-1 examples. Profiles are explicit: `v7-sha3-256` is a candidate; `v3-sha1` requires explicit merchant confirmation. There is no automatic fallback. Original encoded callback bytes are verified with constant-time signature comparison before parsing; duplicate JSON keys/nonfinite values and correlation mismatches fail closed. A status response is trusted only from a bounded, authenticated request to the fixed official HTTPS endpoint, never an arbitrary return body.

Before any genuine Sandbox acceptance, confirm public/private key syntax, merchant/environment, API version/algorithm, checkout fields, sandbox status/flag semantics, signed original callback shape, unique payment identity, status response identity/amount/currency/action, status taxonomy and provider timeout/retry behavior. Capture **redacted** evidence of Standard, Premium, add-on, duplicate/concurrent callback, invalid signature/correlation, lost callback→status recovery, expired/void/excess money and reversal behavior. Never put credentials, card data or full payer payloads into logs/artifacts.

Reversals use a separately gated candidate envelope with original `payment_id`, unique `refund_id`, exact `refund_amount` and full original payment correlation. Ambiguous refund/chargeback messages remain reviewable and do not silently undo paid history. Cumulative reversals are bounded; full reversal removes that interval from subsequent snapshots; partial reversal records exact money while retaining service access until the paid base is fully reversed. Outgoing refund requests are not implemented/enabled.

Recurring requires explicit versioned consent, prior confirmed manual payment, provider subscription identity, next cycle date, unique invoice/order per provider cycle and confirmed cancellation semantics. The current candidate expects `action=subscribe` enrollment with `subscription_id` and `next_payment_at`, and `action=pay` cycle evidence with the matching `subscription_id` and unique canonical cycle order. **These fields/cycle-order capability are not asserted to match a real merchant account.** Merchant approval may require a reviewed adapter change. `prepare_cycle` creates metadata only; no scheduler initiates charges or competes with provider retries. Registration/cancellation commands are prepared, never autonomously sent. `subscribed` does not settle money. Cancellation is pending until signed provider confirmation, with all paid access preserved.

Wallet/referrals are sandbox preparation only. Legal funding/custody/accounting/tax, permitted LiqPay flows, referral funding/hold and payout rules require owner/legal/provider decisions. Real topups/transfers/payouts have no enabled endpoint. Test captures post to the sandbox ledger without settling an invoice or activating service. Referral policy v1: first confirmed base payment only, 20%, 14-day hold; reviewed immutable policy versions support 25/30%. Existing attribution retains its policy version. Refund/chargeback compensates the corresponding reward once, including after creation flags are disabled. Test funding is not reward eligibility.

## Product compatibility and migration

Existing UUID orders stay on the legacy v3/SHA-1 callback and existing payment/subscription tables. Only canonical `carpot-sandbox-…` / `carpot-production-…` orders route to Core; verification failure never falls back to legacy. Legacy callbacks use their original configured keys; no global credential replacement.

Approved source prices: Warehouse Standard 1000 UAH/month (10 cars, 5 employees excluding owner), Premium 4500 (50/10); existing add-on SKUs 300/1200/2000 for +1/+5/+10, prorated by integer minor units to the end of the current paid base. Base renewal/plan change applies to the next unpaid period; no guessed immediate upgrade credit. Trial remains 10 days once per canonical company, without card, with immutable deadline across plan changes. Canonical garage 99/199/299 UAH for 1/5/10, 30 days; CRM 99 UAH/30 days; Standard site 499/year. Site Plus 1499 and custom from 4999 remain quote/fulfillment-gated because exact execution/renewal terms are not defined in the source. A non-default legacy CRM environment price needs an approved immutable catalogue version before rollout. Never silently map an unmatched amount.

Use the read-only legacy export preview to find duplicates/unmapped history. `map_verified` can reference only an existing canonical invoice/settlement with matching verified provider evidence. A legacy status is insufficient. Historical payments without independently correlated evidence remain legacy; do not synthesize settlements, reset subscriptions, overwrite site configuration, or delete history. Fresh canonical subscriptions preserve active legacy garage capacity. New canonical periods are continuous and do not accumulate credits. Only sites created with explicit global fulfillment provenance expire under the new projection; legacy sites are preserved. CRM projections retain existing/free access.

Bindings use trusted server ownership identities. Do not infer cross-service company identity from email/username/phone. Linking an existing account requires explicit verified ownership/evidence; unattended migration of existing identities is not enabled. The current product adapter creates a product account when no reviewed cross-service mapping exists. A single company-wide cabinet for independently owned legacy product accounts therefore needs reviewed linking before those histories can be shown together.

## Railway deployment preparation — not executed

Project `selfless-caring` (`ff2f3a14-2ffa-49ba-9b9d-9889ce98da5d`). Existing Warehouse staging `e9d04365-fc5a-4ba2-84a7-275c44580fe8`, Catalogue staging `56997e2a-48d3-4e09-88b5-01754c383cb3`; neither was changed.

Prepare a separate `carpot-billing-sandbox` API and dedicated sandbox PostgreSQL inside the existing project **only after explicit resource/deployment approval**. Root build context, `bot/billing/Dockerfile`, Railway config `bot/billing/railway.toml`; image excludes browser fixture drivers and runs as UID10001. Health `/health`, schema/environment readiness `/ready` (009). No migration at server startup. No database volume shared with Warehouse/legacy bot. Require TLS verify-full and the appropriate CA for non-loopback connections. Never relax certificate verification merely to accept a provider endpoint.

Provision separate NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOINHERIT migrator-owner and application identities, with credentials supplied by the approved secret mechanism. Application must not be an owner or member of the migrator role. Use a dedicated database, revoke PUBLIC connect as appropriate to its operational environment, grant CONNECT explicitly to both roles. Run `python -m bot.billing.api migrate` with only the explicit migrator DSN; it seeds immutable catalogue terms. Then run `bot/billing/deploy/grants.sql` as the migrator via psql `-v app_role=billing_app -v ON_ERROR_STOP=1`. The application has no DDL/DELETE/TRUNCATE/catalogue/schema-version rights. Row-lock privileges are narrowly granted; immutable account/member identity and financial triggers retain evidence. Local acceptance tests exercise the actual role grants through checkout/settlement/reversal and forbidden operations.

Deploy API with the application DSN only. Separate environments require separate databases, credentials, peer keys and origins. The runtime must not receive `BILLING_MIGRATOR_DSN` or legacy `LIQPAY_*` secrets. Network egress destinations are fixed/explicit and redirects rejected. Status polling/outbox: explicit `python -m bot.billing.api work-once`, bounded batches and flags OFF by default. No startup worker; no recurring charge/payout worker. For a future scheduled service, supply only the app identity and relevant network/delivery flags after approval.

Warehouse global image is separately prepared at `warehouse/deploy/railway/backend-global.Dockerfile` (root context; shared transport/model SDK only). Current staging image/config selection is unchanged. Explicitly apply additive Warehouse migration `b23c45d67e89` from `a12b34c56d78`; keep global flag OFF until binding/environment/peer checks are accepted. Existing frontend nginx permits the exact official LiqPay form origin. Select the new image/build context only through an approved staging rollout.

For the bot, install `bot/billing/requirements-product.txt` alongside existing requirements in a reviewed future image; flags OFF use lazy SDK imports and retain legacy dependencies. Explicitly apply the additive bot projection SQL using the legacy application's migration procedure, then enable one product at a time in sandbox. Do not copy Finance DB credentials into either consumer.

## Variables (names/purpose only; all independent of legacy LIQPAY_*)

| Variable | Purpose/default |
|---|---|
| `BILLING_ENVIRONMENT` | Required `sandbox` or `production`; pinned in DB identity. |
| `BILLING_OPERATIONAL_DSN` | Required runtime app identity; explicit DSN, TLS verify-full remotely. |
| `BILLING_MIGRATOR_DSN` | Operator migration command only, never runtime. |
| `BILLING_LIQPAY_PUBLIC_KEY`, `BILLING_LIQPAY_PRIVATE_KEY` | Dedicated environment merchant credentials; never browser/consumer/log output. |
| `BILLING_LIQPAY_PROFILE` | `v7-sha3-256` candidate or explicitly confirmed `v3-sha1`. |
| `BILLING_RESULT_URL`, `BILLING_CALLBACK_URL` | Separate explicit public HTTPS return/callback URLs; return only locates an order. |
| `BILLING_MERCHANT_CONFIRMED` | false; merchant-specific manual/status profile acceptance. |
| `BILLING_LIVE_ENABLED` | false; separate explicit production financial gate. |
| `BILLING_CHECKOUT_ENABLED` | false; manual checkout rollout. |
| `BILLING_PROVIDER_NETWORK_ENABLED` | false; bounded official status queries. |
| `BILLING_REVERSALS_CONFIRMED` | false; separately verified incoming reversal envelope. |
| `BILLING_PEER_KEYS_JSON` | Required map of dedicated per-peer secrets, minimum32 bytes; no legacy secret reuse. |
| `BILLING_PEER_PRODUCTS_JSON` | Binding allowlist; default Warehouse→warehouse, Telegram→garage/site/seller_crm. |
| `BILLING_ENTITLEMENT_URLS_JSON` | Explicit peer→HTTPS consumer receiver addresses. |
| `BILLING_DELIVERY_ENABLED` | false; replayable outbox network delivery. |
| `BILLING_ADMIN_PEERS` | Empty; explicit reconciliation-reader peer allowlist, still account/owner scoped. |
| `BILLING_PUBLIC_ORIGIN`, `BILLING_PUBLIC_LINK_KEY` | Optional dedicated public Billing origin and separate random HMAC key for expiring Telegram hosted capabilities. |
| `BILLING_RECURRING_ENABLED`, `BILLING_RECURRING_CONTRACT_CONFIRMED` | Both false; separate capability/contract gates, plus merchant confirmation. |
| `BILLING_WALLET_TEST_ENABLED`, `BILLING_REFERRALS_TEST_ENABLED` | false; sandbox only; cannot enable real wallet/payout. |
| `WAREHOUSE_GLOBAL_BILLING_ENABLED` | false; existing pilot behavior retained. |
| `WAREHOUSE_BILLING_ENVIRONMENT` | Explicit sandbox/production; must match WAREHOUSE_ENV local/staging or production respectively. |
| `WAREHOUSE_BILLING_API_URL`, `WAREHOUSE_BILLING_SERVICE_KEY` | Explicit HTTPS Billing API and dedicated Warehouse peer key; no Finance DSN. |
| `WAREHOUSE_GLOBAL_BILLING_MODE` | compatibility/dry_run/enforce; default dry_run. |
| `BOT_GLOBAL_GARAGE_ENABLED`, `BOT_GLOBAL_CRM_ENABLED`, `BOT_GLOBAL_SITES_ENABLED` | false; independent staged product routing flags. |
| `BOT_BILLING_ENVIRONMENT`, `BOT_BILLING_DEPLOYMENT` | Explicit sandbox+local/staging or production+production. |
| `BOT_BILLING_API_URL`, `BOT_BILLING_SERVICE_KEY` | Explicit HTTPS API and dedicated Telegram peer key; no provider secret/Finance DSN. |

`WAREHOUSE_E2E`, `CARPOT_BILLING_BROWSER_DSN`, `BILLING_BROWSER_FIXTURE_KEY` and synthetic driver keys are acceptance-only and must not be deployed to an operational service. Existing `LIQPAY_PUBLIC_KEY`, `LIQPAY_PRIVATE_KEY`, `LIQPAY_CALLBACK_URL` remain unchanged and do not imply merchant-contract confirmation.

## Rollout and rollback

After approval: dedicated sandbox resource/roles → explicit migrations/grants → API readiness → genuine merchant Sandbox acceptance → consumer compatibility/dry-run → reviewed owner binding → signed delivery/ack and quotas → small enforce rollout. Production needs a separate merchant/live decision and production DB/keys; recurring and wallet remain independent gates.

Rollback disables checkout/product/recurring-creation/delivery flags and rolls back code. Keep migrations, bindings, all invoices/intents/evidence/settlements/journal/reversals/rewards/outbox and legacy history. Do not drop columns or reverse money destructively. Correct via forward migrations/compensating entries. Reconcile outstanding provider payments/cancellations and replay the latest full entitlement snapshot before re-enabling consumers. A code rollback cannot cancel a provider mandate; do not report it canceled without confirmation.
