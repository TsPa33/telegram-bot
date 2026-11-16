# Checkpoint 009 — staging password-only access and real Warehouse Directory

Date: 2026-11-16 UTC. Owner-authorized change from `e0d959aed11f258ffa7d2bcc208edf1efbfe9c98`.
PR: https://github.com/TsPa33/telegram-bot/pull/539 (Draft, not merged).

## Release and deployment

- Deployed code SHA: `a3fa81ee322a081b0e23afd0639fa114cc2792bc`.
- Railway deployment: `8fb3c325-3766-40e1-8a6c-c069804d3dd8` — **SUCCESS**.
- Project: `ff2f3a14-2ffa-49ba-9b9d-9889ce98da5d`.
- Environment: `warehouse-staging`, `e9d04365-fc5a-4ba2-84a7-275c44580fe8`.
- Service: `carpot-control-preview`, `14ec32b1-c1dc-4362-be91-a3e608212832`.
- URL: https://carpot-control-preview-warehouse-staging.up.railway.app/control/
- Prior release: deployment `8486a7b7-33af-43c9-bc6e-22591095f3b2`, SHA `e0d959a`.

The inspected non-destructive Railway patch `9da1f266-a551-4d0a-a2ad-6cd13048b62a`
contains exactly three changes to this CRM service: pinned code SHA and two new
policy variables. `CONTROL_CENTER_AUTH_MODE=password-only` and
`CONTROL_CENTER_PASSWORD_ONLY_ENVIRONMENT_ID=e9d04365-fc5a-4ba2-84a7-275c44580fe8`.
No shared variables or other service changes were included. Build, start command,
TLS CA handling, domains, limits, healthcheck and existing variable names remain.
No DB migration, reset, re-seed or live operator SQL command was run.

## Implemented behavior

Password-only is an explicit server policy. On Railway it additionally requires
source environment staging, actual runtime name warehouse-staging and the matching
actual environment ID. Local mode requires a loopback/test origin and no Railway
environment identity. Default, production, mismatched ID/name and unknown policy
remain MFA. Password-only sessions have a different audience and mfa_verified=false;
MFA mode rejects them. Copying staging settings into production cannot activate
this mode while production retains its actual runtime identity.

The login form fetches policy before enabling submission and hides Authenticator in
simplified mode. Argon2, durable account/IP budgets, exact Origin and session-bound
CSRF, HttpOnly/Secure/SameSite cookies, actor assertions, session revocation, RBAC and
append-only safe audit remain. All staff can change their own password in Settings;
it revokes all their sessions. Privileged changes require current-password step-up
under simplified policy or fresh single-use MFA under the default policy.

Combined MFA enrollment/rotation is disabled in simplified mode. At startup preview
Owner MFA keys are retired once using fresh unshared random material, old sessions
are revoked and auth.mfa_retired is audited. **Runtime confirms one Owner key was
retired.** This cancels pending session-bound enrollment and replaces any already
activated preview key without reading/reusing a screenshot key. The Owner password
and service MFA encryption key are unchanged. Secure operator re-enrollment is
required before this same preview database can return to MFA mode; there is no web
recovery/bypass or restoration of the old seed. Production credentials are untouched.

Automatic Warehouse refresh uses existing ENABLED/AUTO_SYNC/PREVIEW/staging-source
configuration and signed staging HTTPS transport. It no longer depends on any staff
login, password change or MFA rotation. Real source responses archive demo company
and link namespaces without deleting their notes/history. Telemetry contains
aggregate counts/coverage/freshness only, never contact details or source identifiers.

## Targeted verification

- **60 backend tests PASS**, including the inherited staff/security/projection tests,
  runtime identity policy matrix, password sessions, CSRF, logout, inactive accounts,
  persistent login budgets, password change/revocation, MFA-default behavior,
  retirement idempotence, pending enrollment rejection, RBAC/step-up, preservation of
  companies/links/grants/notes/tasks and rotation-independent real-source projection.
- **4 password-only browser cases PASS**: Chromium and WebKit at 320/1440; login with
  no MFA field, current-password change, CSRF proof recovery, logout and unauthorized
  responses against the real local API and disposable PostgreSQL.
- **32 existing MFA browser cases PASS**, both engines, four widths and four themes.
- Frontend production and staff-only builds PASS; changed Python lint checks PASS
  (existing ambiguous-name E741 is excluded). No full Warehouse rerun was needed.
- Local logs: `/workspace/cc-password-targeted-final.log`,
  `/workspace/cc-password-targeted.xml`, `/workspace/cc-password-browser-final.log`,
  `/workspace/cc-mfa-browser-final.log`, `/workspace/cc-password-control-build.log`.

Commits use [skip ci] to avoid automatically repeating the long unchanged Warehouse
workflow matrix requested to be omitted. These are local targeted passes; no new
independent CI result is claimed. The prior four-workflow success belongs to e0d959a.

## Actual staging acceptance

At 2026-11-16 12:37:08 UTC the system-trust HTTPS client observed health 200 and
status 200 with enabled=true, environment=staging, auth_mode=password-only. Anonymous
me/CSRF/overview/logout/password-change returned 401; login without Origin returned
403. Responses are no-store. Railway reports SUCCESS and live pinned SHA a3fa81ee.

External WebKit rendered the deployed mobile login page with certificate verification
enabled: one username input, one password input, zero MFA inputs, no JS errors.
The previous Chromium local trust-store limitation was not bypassed. Local public
evidence and non-sensitive screenshot: `/workspace/control-password-acceptance/`.

Runtime startup: `control.auth mode=password-only retired_owner_mfa=1`.
The **first automatic signed real-source sweep** completed before any Owner login:

| Aggregate | Observed |
| --- | --- |
| Real staging workspaces | 5 |
| Owners / employees | 5 / 2 |
| Verified Warehouse links | 5 |
| Verified Billing links / unlinked workspaces | 0 / 5 |
| Conflicting / invalid links | 0 / 0 |
| Archived demo companies / demo in real directory | 5 / 0 |
| Coverage | sweep_complete |
| last_success | 2026-11-16T12:35:41.423617+00:00 |
| Freshness at successful sweep | 0 seconds |
| last_error | null |
| Projection/source contract schema marker | 1/c34d56e78f90 |

These are observed staging projections, not production counts, revenue, financial
mutations or a census with source tombstones applied. The schema marker is the
existing projection contract marker, not a new independent source migration audit.
No PII was printed. Demo remains archived, preserving its operational history.

All other staging service deployment IDs and every volume inventory entry match the
pre-change snapshot. No production deployment, other service mutation, financial
operation, customer message or Telegram/Sites integration was performed.

## Remaining human acceptance and resume

Owner's actual staging login/logout with the existing password awaits Owner feedback.
The agent has no Owner browser session/password and does not request secrets in chat.
Automated password login/change/logout are verified on disposable fixtures; actual
staging form, policy, health and real-source loading are independently observed.
Do not mislabel fixture login as a real Owner session test. No data-loading blocker
remains; the first real directory load is confirmed above.

Resume: verify the same deployment and collect Owner login/logout feedback. Keep
Telegram/Sites integration deferred until this final human acceptance is complete.
The rollout pins the code SHA; a later documentation-only checkpoint commit does not
change the running code or require another deployment/full test cycle.

Rollback must be scoped to CRM and reviewed with the MFA retirement in mind: restoring
MFA-only code against the retired preview seed requires secure Owner re-enrollment.
Do not restore a disclosed MFA seed, drop schemas, reset credentials casually, delete
audit/notes/links or touch customer/finance history. No rollback was performed.
