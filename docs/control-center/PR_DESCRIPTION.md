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

- Targeted staff security/projection, model/unit/build і real React browser tests
  описані в Checkpoint 012 та implementation report.
- Manual Control Center gate може пропускати довгий Warehouse domain regression
  через `warehouse_full=false`; звичайні PR/push gates залишаються незмінними.
- Browser acceptance використовує лише disposable synthetic local PostgreSQL/API.
  Це не приймання живого staging або перевірка його Directory freshness.

Документація: `docs/control-center/Checkpoint_012_Review_02_Implementation.md`,
`implementation-2026-11-17/IMPLEMENTATION_REPORT.md` і попередні checkpoints001–011.
У цьому пакеті Railway deployment/merge/main/production не виконуються.
Після code review потрібен окремий контрольований staging rollout.
