# Checkpoint 012 — Review 02 у React Global CRM

17 листопада 2026, Київ. Repo `TsPa33/telegram-bot`,
`feature/carpot-control-center-warehouse`, Draft PR #539.
Вихідний дизайн і перевірений remote head:
`3a1e3d664b6f11aa644da02310fc5f91a9846596`.

## Provenance

Implementation SHA — перший commit, що додає цей checkpoint:

```sh
git log --diff-filter=A --format=%H -- docs/control-center/Checkpoint_012_Review_02_Implementation.md
```

Повний SHA і незалежний CI run будуть наведені у release receipt та фінальному
handoff. Наступні коміти до початку цієї роботи не виявлено; перед push head
перевіряється повторно. Force push, merge/main і Railway deployment заборонені
межами цього пакета.

## Реалізовано

Корпоративний Review 02 впроваджено в чинний React stack: Global shell,
breadcrumbs/hash routes, чотири теми, компактний scoped огляд, server-paginated
каталог і responsive cards, повний клієнтський профіль із сімома вкладками,
робоча черга, task dialog/status updates, notes/assignment, налаштування безпеки.
Старий CompanyPreview modal замінено profile page.

Докладна матриця компонентів, джерел даних, екранів і меж —
[`IMPLEMENTATION_REPORT.md`](implementation-2026-11-17/IMPLEMENTATION_REPORT.md).

ACTIVE не позначається як оплата; UNKNOWN/access_incomplete не стає FREE.
Неперевірений операційний доступ і payment evidence мають окреме пояснення.
Невідомі показники не підмінено нулями. History/activity/revenue без потрібного
контракту мають unavailable state; жодних synthetic чисел у робочому frontend.

## Незмінні межі

Backend runtime, auth transport, CSRF/RBAC/audit/session policy, Argon2/MFA,
Warehouse Directory sync, entitlement formulas, Warehouse/Billing domain code,
БД і міграції не змінено. У `api.ts` змінено лише три display labels;
у SecuritySettings — лише accessible form names. Backend diff — виключно
opt-in disposable browser fixture. Реальні credentials/дані/flags не читалися.
Telegram/Sites/Billing integration не починалася.

## Перевірки

- Staff security/projection backend: **60 PASS**, disposable local PostgreSQL,
  JUnit без failures/errors/skip.
- Нові route/filter/cursor/status/null/urgency unit cases: **5 PASS**.
- `npm run build`: **275 PASS** чинного prebuild unit gate, TypeScript і Vite PASS.
- Окрема staff-only TypeScript/Vite build: PASS.
- Scoped Manager/Support/Administrator, Chromium/WebKit: **6 PASS**; server scope,
  contact masking і відсутність заборонених finance/staff запитів.
- Resilience, Chromium/WebKit × 390/1440: **4 PASS**; overview503 не дає нулі,
  запізніла відповідь клієнта не змінює інший профіль, notes503 не блокує Products,
  довге ім'я не створює document overflow.

- Основна real React browser matrix: **32 PASS** — Chromium/WebKit ×
  320/390/768/1440 × Light/Forest/Gold/Onyx; profile sections, cursor refresh,
  notes escaping/persistence, task creation/status, focus, drawer, logout/revocation.
- Password-only через той самий React UI: **4 PASS** — обидва engines ×320/1440,
  login/password change/relogin, CSRF recovery, logout401.
- Source boundary, auth transport comparison, workflow YAML та whitespace: PASS.

Незалежний CI receipt фіксується окремо після завершення запуску.
Локальні результати не видаються за GitHub Actions success.
Попередні 639 frontend або 1025 Warehouse результати не видаються за новий запуск.
Повний багатогодинний Warehouse regression не запускався: domain code незмінний.

## Готовність та обмеження

Локальний targeted gate пройдено. Пакет потребує незалежного CI та code review перед окремим staging
rollout. Staging/runtime acceptance і реальна Directory freshness цією роботою
не перевірялися. **Deployment ID відсутній: Railway не розгортали.**

Повна історія/детальна activity stream/activity sort/global attention aggregate/
MRR/churn/revenue залишені до окремого API-пакета. Tasks/notes/finance обмежені
чинними серверними вибірками. Призначення нових tasks — чинному staff; нових
прав або довільного task reassignment немає. Доступність перевірена цільовими
keyboard/browser scenarios, не blanket WCAG certification.

Після завершення implementation/code review зупинитися перед Railway.
