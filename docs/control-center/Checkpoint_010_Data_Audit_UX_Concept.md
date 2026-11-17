# Checkpoint 010 — аудит даних і концепція корпоративного Global CRM

17 листопада 2026, Київ. **Аудит і ізольовані макети завершені; реалізація у робочій CRM не розпочата.**

## Фактичні версії

- Репозиторій TsPa33/telegram-bot, feature/carpot-control-center-warehouse, Draft PR #539.
- Перевірений checkout / PR head до концепції: `4f06cfe274d945493301066284a718a92a869a10`.
- Фактичний CRM release: `a3fa81ee322a081b0e23afd0639fa114cc2792bc`.
- Railway warehouse-staging / carpot-control-preview, deployment
  `8fb3c325-3766-40e1-8a6c-c069804d3dd8`, SUCCESS; source pin перевірено read-only.
- e0d959a з user context — історичний попередник, не поточний deployment.
- Концепція: commit, який додає цей checkpoint; точний SHA повертає
  `git log -1 --format=%H -- docs/control-center/Checkpoint_010_Data_Audit_UX_Concept.md`.
  Commit містить лише docs/control-center/, deployed SHA не змінюється.

## Результати аудиту

34/10 — не доведена помилка. CRM бере тарифний usage із Warehouse: унікальна множина
неархівних авто й донорів із залишками/резервом, включно з архівними; provenance
враховується за domain feature policy. Active addon додаються до обраного base/trial/
grace capacity. Активні працівники рахуються без власника; people включає також
вимкнених accounts. Склад конкретних 34, активні пакети й runtime-mode компанії
не перевірені — немає read-only агрегату конкретного workspace чи Owner-сесії.
Тарифна формула і реальні дані не змінювалися.

Підтверджена UX/семантична проблема: ACTIVE показано як «Оплачено», хоча це entitlement
interval, а domain paid=true також застосовується до trial/grace. FREE не доводить
існування безкоштовного плану. UNKNOWN при відсутній projection захищено адаптером;
не перетворювати його на FREE/несплату. Оплату, доступ, тариф і достовірність розділено
в запропонованій концепції. Перевищення квоти не означає несплату.

Read-only runtime receipts: 5 staging workspace-компаній, 5 власників, 2 працівники,
5 verified Warehouse links, 0 verified Billing links, 5 unlinked, 0 conflicts/invalid
links, 5 archived demo і 0 demo у реальному каталозі. Last success на момент читання:
17.11.2026 08:31:28 Київ (06:31:28.526702Z); sweep_complete, last_error=null,
refresh приблизно раз на 5 хвилин. Freshness=0 у log — вік при завершенні sweep.
DB uniqueness constraints перевірені у code; дедуплікація фізичних осіб/юркомпаній
між продуктами не доведена. Tombstone automation залишається відкладеною.

## Артефакти

Каталог: `docs/control-center/concept-2026-11-17/`.

- DATA_AUDIT.md — короткий аудит із provenance, причинами, невизначеностями та рекомендаціями.
- UX_AND_PLAN.md — аудит overview/list/profile/queue/sidebar/settings/mobile, структура
  Global CRM, component tree та план одного пакета після погодження.
- index.html / style.css / app.js — ізольована offline-concept, не частина Vite build.
- preview.html — один самодостатній HTML для локального перегляду.
- review.html — галерея 5 пов'язаних макетів; mobile.html — мобільний preview.
- screenshots/01–05 — overview, list, profile, work queue, mobile; 06 — Forest Slate.
- verification/ — sanitized JSON receipts нових preview-перевірок.

Вигадані 12 компаній і chart series не є реальними staging-даними. Email `.invalid`,
контакти синтетичні. Ніяких external calls, credentials, PII чи фінансових операцій.
Майбутні Telegram/Garage/Sites/Billing/referral modules явно План/disabled.
Теми: Light / Onyx / Midnight Gold / Forest Slate. Меню дворівневе; плавне відкривання,
швидке закривання; mobile menu, картки клієнтів/задач і повний профіль.

## Виконані перевірки

Новий prototype only: Chromium і WebKit, 4 теми, 4 ширини (320/390/768/1440), 5
екранів — 32 конфігурації / 160 screen checks, 0 document overflow / JS errors /
external HTTP requests. Чотири interaction cases: filters/search/empty/pagination,
профіль і demo-finance permission, notes isolation/escaping, task composer, submenu,
mobile menu/ESC. Самодостатній file:// HTML успішний в обох engines. Візуально
переглянуто головний огляд, профіль, mobile і Forest Slate; фінальні PNG згенеровано.
Node syntax і git diff whitespace check виконані. Повний Warehouse, попередні 60
backend tests і 36 auth browser cases не повторювалися: working code не змінювався.

## Блокери та наступний крок

Потрібне погодження власником концепції, термінів доступу/оплати і меж наступного UI
пакета. До цього жодної інтеграції у working CRM. Окремо бракує read-only quota
breakdown конкретних 34/10, scoped activity aggregates/daily series і verified payment
source. Вони не підмінені вигаданими production метриками; demo series лише макет.

Після погодження: маршрути та shell → compact directory → profile sections → work
queue → вузькі погоджені read-model доповнення → targeted UI/RBAC/accessibility tests
→ review. Для staging rollout знадобиться окрема авторизація, це завдання її не дає.

Не було merge, deployment, setter variables/flags, DB/migration/price/finance changes,
production/Telegram/Sites/Billing operations, email/Slack/customer messaging.
Working frontend/backend і Railway конфігурація не редагувалися. Existing PR лишається
Draft; підготовлено reviewable documentation/concept package для власника.
