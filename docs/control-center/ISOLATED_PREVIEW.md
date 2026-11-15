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

## Railway isolated preview bootstrap
The separate preview DB image uses the official PostgreSQL 16 entrypoint and a new persistent volume. It refuses a database name other than carpot_control_preview. TLS certificate/key are supplied as secret variables, with a hostname-matching trusted certificate on the app. Schema owner and operator are NOLOGIN; runtime is restricted. Initial Owner password hash and encrypted MFA seed are supplied only via private Railway variables; never committed. The five fictional records are seeded only on fresh PGDATA. No real data adapter is configured. Initial owner credentials are delivered via the authorized Railway dashboard and must be rotated before any real-data access. Demo staff cannot authenticate. The bootstrap image is preview-only, not a migration path to production.
