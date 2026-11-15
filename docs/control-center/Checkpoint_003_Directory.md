# Control Center checkpoint 003 — Warehouse directory and scope

Date: 2026-11-15 Europe/Kyiv. Branch: feature/carpot-control-center-warehouse.
Base fdaef3c638765ca845692727f90c9f140395891b.
Verified implementation 4e4a5f07e6f977d967b4b9d9277d929c61055adb.
PR pending, API Forbidden; pushed code is available for review.

Implemented: distinct company ID for a Warehouse owner workspace; employees are
people, not companies. Namespaced source/evidence links, unlinked/conflict/
revoked states; no email/phone/UUID merge and no financial binding writes.
Source env mismatch is conflict. Assigning a replacement manager revokes its
predecessor's grant; Support receives explicit minimal company context.
Backend scope precedes list/search/detail/notes/finance/tasks. Cursor pagination,
bounded size, sort, plan/status/link/manager/Kyiv date filters are server-side.

Warehouse reads use dedicated restricted credentials, explicit schema-head
validation, REPEATABLE READ READ ONLY, connection/statement/lock timeouts and
<=100-owner batches. Only selected non-secret source columns are granted.
Reuse entitlement state/usage; last login separate from partial business
activity; continuous base coverage merges prepaid adjacent periods, not trials.

Projection sweeps use (created_at,id), atomically commit rows/cursor, replay
idempotently and repeat from the beginning after a complete sweep. This is
bounded reconciliation, not an updated_at assumption. Failed batches retain
the cursor and sanitize errors. Source metadata includes projection/source
schema version, env, watermark, fetched/last-success/error/coverage. No startup
sync, no cross-service N+1 for lists or summary. Source-deleted rows retain notes
and become stale; tombstone propagation is deferred and counts have coverage.

Files: control_center/{projection,models,api,config}.py, source-grants.sql,
control_center_tests/{test_source,test_projection,test_security}.py.
Migrations: part of independent additive 001; no customer schema/index changes.
Tests: included in the 29 PASS suite. Actual migrated source DB proved one owner
plus one employee produces one company; password reads and source writes denied.
Replay/timestamp tie/watermark failure/conflict/environment tests passed.
CI run 43681872714 staff-and-projections successful on exact implementation SHA.
Runtime: local disposable only. Source live env/schema/flags unknown.
Next/resume: financial read checkpoint 004. Rollback: OFF/prior code; keep
source links/company history/notes/audit. No destructive customer changes.
