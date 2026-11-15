# Control Center — isolated preview release plan

Scope: first owner-only design/functional acceptance on synthetic data. No real
customer data, Billing peer, Warehouse source credentials, production variables
or existing-service changes. No live deployment is authorized by this document.

## Prepared runtime
- One public staff-only service using root-context
  `warehouse/deploy/railway/backend-control.Dockerfile`.
- One separate disposable preview PostgreSQL database; schema 001 with
  distinct migration-owner, runtime and operator roles. Do not reuse Warehouse
  or Billing credentials. No new Warehouse Alembic migration.
- Exact HTTPS origin; feature enabled only in preview after approval.
  `CONTROL_CENTER_SOURCE_ENVIRONMENT=staging`; schema identity staging.
  TLS verify-full with valid CA. MFA key unique; no default password/seed.
- Standalone /control/, /api/control/*, /health. Customer API returns 404.
  /health checks runtime role/schema, MFA key and compiled static assets.
- Source/Billing connections absent. Synthetic directory and internal tasks
  may be seeded only through an explicit isolated operator process, with
  visibly fictional company names and example.test contacts. No copies of
  customer stock, photos, sessions or real finance records. Financial details
  explicitly unavailable; no payment commands.
- Provision Owner through the approved secure enrollment procedure in README.
  Do not put a password or MFA seed into Git, deployment command or chat.
- First acceptance: login/MFA, overview, company search/filter/profile, notes,
  queue, assignment isolation, mobile layout and theme.
- Before an actual Railway preview: approve resources and cost, confirm
  database target and TLS/roles, check exact CI revision, verify no existing
  changes staged, then create only isolated resources. No main merge.
- Rollback: disable preview access / stop preview service; leave source domains
  untouched. Remove disposable resources only after explicit approval.

## CI preview evidence
The browser job builds the actual standalone frontend and serves it via the
same dedicated ASGI entry against a disposable loopback PostgreSQL fixture.
It captures the dashboard, client list, desktop/mobile company detail and queue
from real Chromium/WebKit flows. This is test evidence, not a public deployment.
The standalone-image job builds the actual production Dockerfile and checks
non-root runtime, staff-only HTML and import without live configuration.
