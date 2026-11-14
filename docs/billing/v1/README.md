# Phase 1: Financial Foundation

This package implements a local-only provider-neutral financial foundation. It does
not activate live Billing, change Warehouse behavior or claim LiqPay compatibility.

- [Architecture and entities](architecture.md)
- [Versioned business draft](business-rules.md)
- [Provider contract and capability blockers](provider-contract.md)
- [Internal API / inbox / outbox contracts](api-contract.md)
- [Fixture entitlement JSON Schema](entitlement.schema.json)
- [Next Warehouse and LiqPay packages](next-packages.md)
- [Validation and scope evidence](validation.md)

## Run safely

From repository root, in a separate virtual environment:

```sh
python -m pip install -r bot/billing/requirements-test.txt
python -m bot.billing.run_fixture_tests
```

The runner explicitly uses the local Docker socket, creates a fresh tmpfs PostgreSQL
container and two distinct `carpot_billing_*_test` databases, binds only loopback and
removes its own container in finally. It never consumes staging/production URLs.
Requires Docker and access to the pinned official image. Tests reset only disposable
billing schemas, not legacy or Warehouse fixtures. Do not point tests at a forwarded
live database, even if its local name resembles a fixture name.

No deployment or migration is automatic. To exercise local application commands,
both CARPOT_BILLING_FOUNDATION_ENABLED and CARPOT_BILLING_FIXTURE_ENABLED must equal
`true`, and `local_billing(explicit_disposable_dsn)` must be called deliberately.
All other feature flags remain false; no flag enables real provider/production access.

DB migration rollback refuses destructive operations. Operational rollback means
disabling new routing and retaining evidence. Future production integration requires
an independently reviewed database/identity/transport adapter, not weakening test guards.
