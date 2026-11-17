# CarPot Global CRM: Warehouse-first Control Center та Review 02

Окремий staff Control Center надає scoped огляд клієнтів Warehouse без customer
DIRECTOR sessions. Global CRM використовує чинний React entry `/control/`,
окремий staff BFF/API, незалежні проєкції та пакетну read-only синхронізацію.
CSRF, RBAC, audit, hashed revocable sessions, throttling і серверна auth policy
збережені; password-only дозволяється лише за чинною staging/local політикою.

Поточний пакет впроваджує затверджений Review 02: корпоративний shell із чотирма
темами, scoped огляд, server-paginated каталог, повний профіль із сімома вкладками,
робочу чергу, notes/assignment/task dialog та responsive cards/drawer. Замість
ACTIVE «Оплачено» показується «Чинний»; неповні дані лишаються UNKNOWN. Недоступні
історія, деталізована активність і фінансові агрегати не підмінені fixtures.

Новий пакет змінює staff frontend і disposable browser fixtures. Backend runtime,
auth transport, sync worker, entitlement formulas, DB migrations, Warehouse/Billing
domain code та інші продукти не змінено. Наявний role-gated finance read збережено;
нової Billing/Telegram/Sites integration немає.

Перевірки та межі доказів:

- Незалежний CI https://github.com/TsPa33/telegram-bot/actions/runs/44050429380
  на SHA `472d9ad1339c7f714c7b350e98b2932765571650`: 4 jobs SUCCESS.
- Staff security/projection 60, frontend prebuild 275, model unit 5, real React
  browser matrix 32 + role 6 + resilience 4 + password-only 4, Billing compatibility
  145 PASS; TypeScript/build та non-root staff-only image smoke PASS.
- Receipts, screenshots і всі межі — у Checkpoint 012 та implementation report.
- Manual Control Center gate може пропускати довгий Warehouse domain regression
  через `warehouse_full=false`; звичайні PR/push gates залишаються незмінними.
- Browser acceptance використовує лише disposable synthetic local PostgreSQL/API.
  Це не приймання живого staging або перевірка його Directory freshness.

Документація: `docs/control-center/Checkpoint_012_Review_02_Implementation.md`,
`implementation-2026-11-17/IMPLEMENTATION_REPORT.md` і попередні checkpoints001–011.
У цьому пакеті Railway deployment/merge/main/production не виконуються.
Після code review потрібен окремий контрольований staging rollout.
