# Control Center checkpoint 001 — verified baseline

Date: 2026-11-15 Europe/Kyiv. Branch: feature/carpot-control-center-warehouse.
Base/head at package completion: fdaef3c638765ca845692727f90c9f140395891b.
PR: pending creation; GitHub API GET PR538 returned Forbidden in this environment.

Remote main remains 2691e92f497d207fc0b903a1612478a327133849. PR538 and
feature/carpot-referral-onboarding both resolve to the base above. PR534–537
are ancestors. No AGENTS.md found in the workspace or integration tree.
Warehouse migration head: c34d56e78f90. No Control Center checkpoints preexist.
Read auth/deps/models/permissions, entitlement and billing adapters, frontend
Theme/shared/preview, Billing operating contract, referrals onboarding and CI.
The prior audit is available outside the repository under /workspace/reports.

Scope: Warehouse-first directory and internal work queue, separate MFA staff
realm, read-only finance through a dedicated scoped peer when configured.
Excluded: Telegram, Seller CRM, sites, legacy CRM/support, Catalogue/OEM,
customer stock/orders, payment mutation, deployment and live configuration.

Runtime: Railway inventory, PR state, completed exact-head CI unknown.
Checks: Git refs/ancestry only; no inherited test counts claimed.
Dependencies: installing isolated Python environment and frontend npm ci.
Migrations: planned separate control_center schema; Warehouse head unchanged.
Next: staff realm with durable throttling, encrypted TOTP, revoke and audit.
Resume: verify branch/status, read subsequent checkpoints and README; never
use old main as implementation base. Rollback: flag OFF; no live changes made.
