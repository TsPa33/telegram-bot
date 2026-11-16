# Checkpoint 008 — controlled Warehouse staging deployment

Date: 2026-11-16 UTC. **Deployment PASS; authenticated/data acceptance PENDING.**

## Release identity

- PR: https://github.com/TsPa33/telegram-bot/pull/539 (open Draft, not merged).
- PR head verified before deployment: `e0d959aed11f258ffa7d2bcc208edf1efbfe9c98`.
- Deployed exact SHA: `e0d959aed11f258ffa7d2bcc208edf1efbfe9c98`.
- Railway project: `ff2f3a14-2ffa-49ba-9b9d-9889ce98da5d`.
- Environment: `warehouse-staging`, `e9d04365-fc5a-4ba2-84a7-275c44580fe8`.
- Service: `carpot-control-preview`, `14ec32b1-c1dc-4362-be91-a3e608212832`.
- Deployment: `8486a7b7-33af-43c9-bc6e-22591095f3b2`, **SUCCESS**, 2026-11-16 11:59:31 UTC.
- Image digest: `sha256:598129fd36cf3e8710e62ce8c0a52f3719cc5cc0fee9bdf70ad2a23ff330baf8`.
- URL: https://carpot-control-preview-warehouse-staging.up.railway.app/control/
- Previous successful deployment: `d7b2e2f2-df83-4cd2-9ef9-75ba1e88db99`, SHA `2a610afaf90cb62a4e26183dac9e3610eef8bca4`.

## Targeted review and change boundary

Reviewed the delta from the previously deployed `2a610afa`: actor/company row locks,
fresh grant checks, independent MFA/rotation throttles, successful-rotation worker
prerequisite, preserved cookie-bound CSRF recovery, session clearing and deployment
entry point. No migration or startup provisioning was added. The isolated entry
serves staff routes/UI and does not start customer Warehouse workers. Runtime
requires unprivileged PostgreSQL identity, verify-full TLS and schema/environment
identity. Signed source client requires staging, HTTPS and staging response identity;
source refresh remains gated by a successful rotation audit for an active Owner.

Railway patch `5319bbdd-42a2-4739-9d5a-aea6fefa69cb` was inspected before applying:
one non-destructive field change, this service's `source.commitSha` only. No shared
variables, volumes, networking or other services were included. Post-deploy config
comparison confirms all other CRM config fields unchanged. Environment has no pending
patch. Every other staging service's deployment ID and all volume inventory entries
match the pre-deploy snapshot, including both database services.

CRM DB remains service `0911f049-2808-4d99-a395-87674ea127fd`, persistent volume
`1314c242-090a-4936-a8f8-7d98a6307529`; no DB command, reset, seed or migration ran.
No credential, variable or flag setter was invoked. Variable names match before/after;
OAuth redacts their values, so value-by-value equality and source destination cannot
be independently inspected through this connector. Preservation is evidenced by the
single-field patch and unchanged service/deployment inventory, not a secret dump.

## Executed acceptance checks

Railway build logs report healthcheck success; deployment metadata and live service
config both identify the exact release SHA. The application has no public SHA route;
SHA attribution is from Railway release provenance, not an invented health field.

External checks at 2026-11-16 12:00:21 UTC:

| Check | Observed |
| --- | --- |
| `/health` | 200, `status=ok`; DB schema/key/UI checks pass |
| `/control/` | 200; HTML served |
| `/api/control/status` | 200, enabled=true, environment=staging |
| Unauthenticated readiness / overview / CSRF | 401 each |
| Unauthenticated logout / enrollment / rotation | 401 each; no privileged action |
| Cross-origin login with empty input | 403 before credential verification |
| Customer `/api/auth/me` on isolated CRM origin | 404 |
| Invalid Host probe | 403 at edge; application's expected 421 not directly observed |
| Normal public responses | no-store and CSP present |

Eleven public probes match expectations. The additional Host probe establishes edge
rejection only. Local evidence: `/workspace/control-stage-acceptance/public-checks.json`.
No login guessing, synthetic live account, invalid MFA attempts or full regression
rerun was performed. Existing exact-head four-workflow success and 1025 PASS / one
opt-in skip remain the prior code verification, not new staging acceptance evidence.

An additional headless Chromium login-page probe was blocked before rendering by
`net::ERR_CERT_AUTHORITY_INVALID` in this environment's browser trust store. The
system-trust HTTPS client independently returned health 200 with certificate
verification enabled. No TLS bypass was applied; browser rendering is not claimed
as a new successful staging check.

## Pending owner acceptance and blockers

No authenticated Owner browser/session is available to this agent. Desktop/browser
handoff tools are absent in this session, and Railway OAuth exposes neither SSH nor
variable values. No password, MFA seed, session token or one-time code is requested
in chat. Do not bypass MFA, generate a replacement Owner or reset credentials.

Owner must sign in at the URL above and complete the Security screen's password and
MFA seed rotation, then sign in again. Use a newer old-authenticator code than the
login code; preserve the old authenticator until rotation succeeds. If already
rotated, preserve the current credentials and report that state instead.

Remaining acceptance:

1. Authenticated login, same-session CSRF recovery, denied mutation with absent/invalid
   proof, logout revocation and login with the rotated credentials.
2. Successful Owner rotation evidence and worker gate state. Do not infer a successful
   rotation solely from the overview boolean: its query does not filter audit result
   (a legacy denied `auth.rotate` record can affect the display); the worker correctly
   requires `result=success`. This is a UI evidence limitation, not a worker bypass.
3. Automatic first real Warehouse sweep: staging source identity, completed coverage,
   no source error, last_success/fetched_at and freshness age (fresh within 15 minutes).
4. Aggregate real workspaces, owner/employee relationships, verified/unlinked/conflicting
   source links and demo namespace separation. Preserve demo history; no PII output.
   Source tombstone propagation remains deferred; directory count is not a live census.

No aggregate counts or freshness values have yet been observed through an authenticated
session. **Do not mark real-data acceptance complete from public health or CI.**

## Resume / rollback

Resume with the same pinned deployment and Owner acceptance; collect sanitized counts,
coverage and timestamps only. Keep the request pending until Owner input is available.
Do not start Telegram/Sites integration before Warehouse CRM acceptance is complete.

If rollback is necessary, restore only this CRM service's prior successful deployment
after verifying its staging identity. Keep database contents, notes, audit, source links,
credentials and flags. No rollback executed. No merge, production deploy, financial
operation, customer message or other service deployment was performed.

This checkpoint is a local documentation artifact; it does not change the deployed SHA.
