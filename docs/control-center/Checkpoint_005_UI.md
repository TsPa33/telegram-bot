# Control Center checkpoint 005 — compact staff UI and internal queue

Date: 2026-11-15 Europe/Kyiv. Branch: feature/carpot-control-center-warehouse.
Base fdaef3c638765ca845692727f90c9f140395891b.
Verified implementation 4e4a5f07e6f977d967b4b9d9277d929c61055adb.
Draft PR pending API access; published branch, not a deployed application.

Implemented separate /control/ Vite HTML/React entry. Warehouse customer entry,
navigation and business components untouched. Reuses Theme and shared State,
adapts native dialog preview/focus behavior; no copy of stock editor. Overview,
server filters/pagination, company owner/staff/access/usage/link context,
permission-gated read-only finance, internal notes and a personal/scoped task
queue. Manager assignment and next internal action never send external messages.
Unavailable metrics and source freshness have explicit user-facing explanations.
No placeholder menus or invented data for other CarPot products.

Files: frontend/control/index.html, src/control/{main,CompanyPreview,api,style},
vite.config.ts and tests/control-center-browser.mjs. Backend task/notes/read
routes in the independent staff API. Migration: existing additive 001 only.

Local validation: 639 existing frontend unit tests PASS / 0 FAIL / 0 SKIP;
production multi-entry build PASS (existing large Warehouse bundle advisory).
Chromium 16 PASS / 0 FAIL across 320/390/430/1440 x Light/Forest/Gold/Onyx.
Real local authenticated staff API/PostgreSQL with clearly synthetic fixtures;
keyboard opening, focus restore, reduced motion, no page overflow, masked
contacts, note persistence, queue and unavailable finance. Explicit browser
fault injection also checked loading/error/empty/stale presentation.

Independent CI run 43681872714 on exact implementation SHA completed both jobs
successfully; browser job runs the same 32-combination Chromium/WebKit matrix
with no engine override, skips or xfails. Local WebKit itself remains unrun:
cdn.playwright.dev denied and official image pull also Forbidden. Distinguish
that local blocker from the successful independent browser gate.

Non-root prepared image built/imported staff mount successfully, acceptance
fixture files excluded. No application deployed or localhost preview published.
Next/resume: checkpoint 006 for final broad regression and PR/network status.
Rollback: flags OFF/code rollback; retain notes, grants, source links and audit.
