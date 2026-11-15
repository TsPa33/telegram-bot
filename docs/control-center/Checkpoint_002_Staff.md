# Control Center checkpoint 002 — staff realm and audit

Date: 2026-11-15 Europe/Kyiv.
Branch: feature/carpot-control-center-warehouse.
Base: fdaef3c638765ca845692727f90c9f140395891b.
Verified implementation SHA: 4e4a5f07e6f977d967b4b9d9277d929c61055adb.
Draft PR: not created; gh pr create --draft returned GitHub GraphQL Forbidden.
The implementation branch is pushed. No live rollout.

Implemented: independent staff identities, encrypted RFC6238 seeds with secure
operator enrollment, Argon2 password hashes, durable account/IP budgets,
non-replayable MFA counters, four-hour hashed sessions with fixed audience,
separate HttpOnly/SameSite/secure cookie path, exact Origin + CSRF, server-side
logout/reset/role/deactivation revoke and staff row serialization. Owner alone
changes other staff privileges; customer DIRECTOR/Catalogue admin is not staff.
Notes/tasks/assignments/role changes and safe append-only audit are atomic.
Unsupported export/financial mutation/impersonation/public registration absent.

Files: app/control_center/{models,security,config,api,manage,asgi}.py,
control_center_migrations/{001,grants}.sql and security/migration tests.
Migration: independent control_center schema 001, Warehouse Alembic c34d56e78f90
unchanged. Runtime/source roles reject elevated or owner identities; source
cannot read account hashes. Operator and migrator credentials excluded from web.

Tests: complete Control Center suite 29 PASS / 0 FAIL / 0 SKIP, hash-verified
requirements-control-center.lock in /workspace/cc-locked-venv, disposable local
PostgreSQL and restricted cc_app/cc_source roles. Includes RFC vector, MFA
replay/marker/audience, CSRF/origin, revoke, privilege escalation, scoped reads,
masked contacts, missing configuration and rollback after denied audit INSERT.
Independent CI on implementation SHA: run 43681872714, staff-and-projections
and browsers both successful (public GitHub run/job pages). Not Railway evidence.

Runtime: local synthetic API/DB verified; staging/production inventory unknown.
Blocker: GitHub API egress for actual Draft PR creation. No new secret requested.
Next/resume: read checkpoint 003, README and later validation checkpoint; verify
current Git status/SHA before edits. Rollback: flag OFF, prior code, preserve
staff audit, sessions evidence, notes and links; never destructive downgrade.
