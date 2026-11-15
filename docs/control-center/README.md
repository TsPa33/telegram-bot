# CarPot Control Center — Warehouse First

Status: implemented for local review; feature OFF by default. No deployment,
paid resources, live credentials, staff accounts or financial operations made.
Base: PR538 fdaef3c638765ca845692727f90c9f140395891b (Warehouse head c34d56e78f90).
See numbered checkpoints for exact local evidence and remaining external gates.

## Architecture and scope

Separate React entry `/control/` (its own Vite HTML/chunk) and staff API
`/api/control`. Customer navigation/login/permissions are unchanged. Lazy mount
in Warehouse main only when CONTROL_CENTER_ENABLED=true; future extraction:
`uvicorn app.control_center.asgi:app`. No customer auth impersonation.

BFF uses an independently permissioned `control_center` PostgreSQL schema;
read-only Warehouse adapter executes only explicit bounded operator sweeps.
Lists, search, overview, notes and queue query projections only: no live Billing
fan-out. Finance detail is a bounded, explicit read through its own Billing peer.
It never creates a binding, invoice, customer membership or payment.

No Telegram/Seller CRM/sites/legacy CRM/support/Catalogue adapters, no stock,
orders/OEM changes. UI labels only Warehouse and never invents missing metrics.
MRR/churn/cash summaries remain unavailable with explicit reasons; provider
captures, bank payouts and profit are not equated. UTC storage, Kyiv display
and date-filter boundaries. Contacts are masked; PII export has no endpoint.

## Credentials and environment (names only)

- CONTROL_CENTER_ENABLED: false by default, explicit opt-in after review.
- CONTROL_CENTER_SOURCE_ENVIRONMENT: local / staging / production, required;
  schema identity pins this value. It describes the configured source, not proof
  of a Railway deployment. Verify source inventory before live rollout.
- CONTROL_CENTER_ORIGIN: exact public origin, HTTPS outside explicit local mode.
- CONTROL_CENTER_DATABASE_URL: dedicated unprivileged schema application role.
- CONTROL_CENTER_MFA_KEY: dedicated Fernet key, secure secret store, no fallback.
  Back up securely; loss prevents MFA verification. Rotation requires a reviewed
  decrypt/re-encrypt operator operation; do not replace blindly.
- CONTROL_CENTER_WAREHOUSE_READ_URL: distinct, unprivileged SELECT-only source
  role; never Warehouse app/owner credentials. Only explicit sync uses it.
- CONTROL_CENTER_MIGRATOR_URL: schema owner, migration operator process ONLY.
- CONTROL_CENTER_OPERATOR_URL: narrow provisioning/reset role, operator ONLY.
- CONTROL_CENTER_BILLING_URL: exact HTTPS origin without trailing slash/path.
- CONTROL_CENTER_BILLING_KEY: unique >=32-byte dedicated peer secret, never
  reused from Warehouse/Telegram/provider keys. Not a Finance database DSN.
- Billing side: BILLING_STAFF_READ_ENABLED=false, explicit reviewed opt-in;
  add a distinct `control-center` peer to BILLING_PEER_KEYS_JSON securely.

Remote PostgreSQL connections require sslmode=verify-full and appropriate CA.
Never disable certificate or hash verification. Runtime rejects superuser,
role/database creator, schema-owner identities and a mismatched schema version
or source environment. Source reader rejects elevated/account-write identities.
The Control Center app role has no customer or finance table privileges.

## Explicit preparation (not a live rollout authorization)

All tasks already use isolated checkouts: use the existing checkout, not a new
worktree. Work from repository root unless stated otherwise.

1. Create distinct migrator-owner, runtime and provisioning roles using the
   approved operator process. Runtime/operator: NOSUPERUSER NOCREATEDB
   NOCREATEROLE NOINHERIT; no membership in privileged/owner/customer roles.
   Provision CONNECT to the intended database; revoke inappropriate PUBLIC
   access per existing database policy. Do not grant PUBLIC CREATE privileges.
2. Install `warehouse/backend/requirements-control-center.lock` with
   `pip install --require-hashes -r ...`. Customer lockfile remains unchanged.
3. With ONLY the explicit migrator URL, source environment and PYTHONPATH set:
   `PYTHONPATH=warehouse/backend python -m app.control_center.manage migrate`.
   This applies immutable SQL `control_center_migrations/001.sql`, independent
   of Warehouse Alembic. Repeat checks version/environment; no destructive
   downgrade. This does not migrate Warehouse or Billing.
4. As schema owner, execute `control_center_migrations/grants.sql` through psql
   with `-v app_role=<runtime> -v operator_role=<operator> -v ON_ERROR_STOP=1`.
   Runtime cannot CREATE, mutate schema_version or modify/delete/truncate audit.
5. In Warehouse, grant only the listed source reads using source-grants.sql.
   Set the reader's default_transaction_read_only=on and statement_timeout=5s.
   Account password hashes and auth sessions are not readable. Source reads
   additionally enforce REPEATABLE READ READ ONLY and bounded statement time.
6. Provision initial Owner explicitly, with operator URL and MFA encryption key:
   `PYTHONPATH=warehouse/backend python -m app.control_center.manage provision
   --username <staff-login> --role Owner` (one shell command).
   The CLI prompts via getpass for a 12–128 character password, a securely
   delivered Base32 authenticator seed and a current MFA code. Never use a
   hardcoded password or put values in shell arguments/chat/logs. Use a secure
   enrollment channel to put the seed into the staff authenticator. The first
   code is consumed: use the next code to log in. No public staff registration.
7. Explicit source refresh, runtime URL + reader URL, no migrator/operator DSN:
   `PYTHONPATH=warehouse/backend python -m app.control_center.manage sync --limit 50`.
   At most 100 workspaces per batch. Repeat while next_cursor is present; a
   complete sweep resets the cursor. Repeat complete sweeps to refresh existing
   companies. No background process or migration is added to app startup.
8. In frontend: `npm ci`, `npm run build`; serve `dist/control/index.html` for
   `/control/` and proxy `/api/control/*` without rewriting its cookie path.
   Default `/` still serves the customer Warehouse app. `backend-control.Dockerfile`
   is prepared with root build context and the transport-only SDK. It does not
   run migrations, sync, provision or create paid resources at startup.

Keep runtime free of migrator/operator URLs. An isolated schema is not CPU/IO
isolation. Start with Owner-only reads; profile sweep batches on representative
non-live data before scheduling, cap frequency and concurrency. The operator
sync advisory lock prevents concurrent sweep mutation. No network destinations
other than explicitly configured Billing HTTPS are contacted by finance reads.

## Staff policies

Owner sees Warehouse scope globally; Administrator globally but finance requires
an extra flag. Manager/Support require company grants. Support cannot get sums
even if its finance flag is set. Scope is enforced before list/search/detail/
notes/tasks/finance. Owner alone changes roles/active/finance for other staff;
self-privilege edits are rejected. No unsupported refund/export/impersonation
endpoint exists. Assignment replacement revokes the prior manager company grant;
Support assignment adds explicit company context. Deactivation immediately
blocks access and revokes all sessions; role changes/password resets also revoke.

Sessions: separate HttpOnly SameSite=Strict cookie, `/api/control` path, Secure
outside local mode, fixed audience, MFA marker, four-hour expiry. Tokens and
CSRF secrets are hashed in storage; TOTP seeds encrypted. Both account and IP
login budgets are durable; successful TOTP counters cannot be replayed. Exact
Origin on mutations plus session-bound X-Control-CSRF. Sessions and user changes
serialize at staff rows; customer cookies cannot authenticate staff.

Operator reset: `python -m app.control_center.manage reset-password --username
<staff-login>` with operator URL; password prompted, sessions revoked and audit
committed atomically. For MFA recovery use a separately reviewed secure
re-enrollment procedure; no web bypass or fallback key is provided.

Local notes/tasks/assignments/role mutations and their safe audit are atomic.
Audit is append-only and excludes note text/passwords/seeds/tokens/provider
bodies/DSNs. There is no external message-sending integration in this module.

## Identity, freshness and known limits

Workspace = owner Account.id; employees reference workspace_account_id and are
not counted as companies. Local directory ID never creates a customer login,
Billing account or Warehouse right. SourceLink is namespaced by system,
environment, entity type and source ID, with evidence/status/verifier/time.
Email/name matching never merges records. Existing canonical entitlement binding
is referenced; a changed binding/environment becomes conflict, not a merge.
No binding remains unlinked. Missing projection is UNKNOWN, not FREE or paid.

The source adapter reuses entitlement state/usage rules. Trial/Grace access
flags are not revenue. Last login is separate from stock-operation activity;
activity coverage is explicitly partial. Continuous paid end merges adjacent
base intervals, excludes trials/addons and stops at gaps. Finance read returns
latest <=100 records per section with incomplete-coverage metadata, never global
totals. Sandbox and production have separate envelopes/database identity and
remain visibly labeled; no money aggregates mix them.

Sweep cursor uses (created_at,id), not a lossy timestamp-only watermark. Updates
are reconciled by repeating the sweep, not assumed to have updated_at. Each
batch atomically commits rows+cursor; replay/overlap is idempotent. Records no
longer returned by source are retained as historical/stale, preserving notes;
source deletion/tombstone propagation is not implemented. Do not interpret
retained/stale directory counts as a precise live company census. Coverage is
partial_sweep/sweep_complete, never a claim of cross-product global coverage.

Each source state stores environment/schema version/watermark/fetched_at/
last_success/last_error/coverage. Failed batches do not advance cursor; errors
are sanitized. Data older than 15 minutes or a failed source marks stale.
Billing failure is isolated from directory/notes. Finance failures return a
reason, never zero amounts. PII retention/export and MRR/cohort policies still
need owner decisions; not blockers for the useful read-first interface.

## Financial API dependency outside Warehouse

Only `bot/billing/api.py` registration plus `staff_read.py` and dedicated tests.
GET /v1/staff/warehouse/{binding} accepts a dedicated control-center peer and
billing.staff.read transport, warehouse.finance.read capability, exact binding
and workspace, method/path/body digest/nonce/expiry/audience/environment. No
customer membership is minted. A key shared with another peer is rejected.
Only authentication nonce receipts are written; finance tables are SELECT-only.
Old tenant endpoints, checkout, LiqPay, settlement, ledger, refunds, recurring,
referrals, prices and other products are unchanged. OFF returns 404.

## Validation and rollout

See checkpoints for exact executed counts. Reproduction uses only explicit
loopback *_test PostgreSQL databases. New workflow control-center.yml runs
restricted-role tests and Chromium/WebKit x 320/390/430/1440 x four themes.
Existing Billing/Warehouse workflows remain unchanged. A workflow definition
is not evidence that independent CI ran or passed.

Local UI: isolated fixture server + Vite, no real customer data. Required pending
gates must be completed before acceptance; never call staging/production ready
from local synthetic evidence. Railway runtime/deployment/flags remain unknown.

Future approved rollout: verify inventory and SHA -> secure roles/credentials ->
explicit additive migration/grants -> Owner provisioning -> explicit bounded sync
-> authenticated /api/control/readiness + source coverage -> Owner-only feature
opt-in -> monitor customer stock/OEM/order latency. No rollout performed here.

Rollback: flag OFF, restore prior code. Keep staff audit, notes, source links,
customer and financial histories; do not destructive-downgrade or drop schema.
Disabling code does not itself revoke stolen tokens; use operator revocation
and investigate before re-enabling. Do not change unrelated service flags.

Final independent gate: run 43682622139 on 55c10e16 passed all four jobs.
Checkpoint 006 preserves raw broad-suite errors from a mixed-edit execution,
fresh isolated/CI passes, exact limitations and the blocked Draft PR handoff.
Use PR_DESCRIPTION.md after GitHub API access is available; no need to repeat
architecture approval or ask for new credentials. No Draft PR exists yet.
