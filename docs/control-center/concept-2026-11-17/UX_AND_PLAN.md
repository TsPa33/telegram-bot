> Фіналізація Review 02: актуальна специфікація, API mapping і план — у [FINAL_REVIEW.md](FINAL_REVIEW.md). Нижче збережено вихідний аудит. Денний графік і повна вигадана стрічка подій вилучені з фінального preview; activity-sort disabled до контракту. Компоненти ще не інтегровані у CRM.

# UX-аудит, структура та план одного пакета

17 листопада 2026. Аудит чинного frontend за source code на 4f06cfe2; нова
авторизована live-сесія не виконувалася. Візуально перевірені саме ізольовані макети.
Робочі frontend/backend файли не змінені.

## 1. Поточний інтерфейс: що зберегти, що змінити

| Область | Підтверджений стан | Рекомендація |
| --- | --- | --- |
| Огляд | Warehouse у заголовках; ACTIVE названо «Оплачено»; великий окремий блок недоступних фінансів | Global CRM shell; компактні показники; відокремити стан тарифу від оплати; недоступні фінанси — коротким повідомленням |
| Клієнти | Grid-кнопки замість таблиці; не видно бізнес-активності й відповідального; тариф — free-text filter | Таблиця/мобільні картки, структуровані фільтри, контакт, продукт, тариф, доступ, реєстрація, бізнес-активність, менеджер |
| Дата у списку | Stale повідомлення підміняє дату реєстрації | Дату зберігати; freshness — окремим індикатором |
| Профіль | Довгий modal із багатьма секціями; немає URL профілю та секцій | Сторінка компанії з глибокими посиланнями і сімома розділами; modal лишити тільки для швидкого preview за потреби |
| Завантаження профілю | Promise.all залежить також від notes/staff | Незалежні loading/error states; помилка нотаток не приховує отриманий профіль |
| Ліміти | «Автомобілі / місткість» не пояснює occupied donors | «Тарифна місткість», progress + перевищення + визначення; окремо активні працівники |
| Доступ/оплата | Один status label змішує entitlement з фінансовою семантикою | Незалежні AccessBadge, PlanPeriod, PaymentEvidence, DataConfidence |
| Черга | Є клієнт, дія, assignee, due/status; немає пріоритету/зручних груп | Групи відкриті/у роботі/прострочені/завершені, зв'язок із профілем, похідна терміновість |
| Меню | Пласка Warehouse-навігація | Компактний дворівневий shell; джерела з capability state, майбутні модулі недоступні |
| Безпека | Уже є password-only staging та окрема MFA-policy | Зберегти; не повторювати enrollment, не переносити політику у frontend; звичайні налаштування окремо |
| Mobile | Є адаптивні правила і modal focus handling | Зберегти accessibility; картки замість обрізаної таблиці, повний профіль, кероване меню, touch targets |
| Теми | 4 корпоративні теми існують | Спільні токени, спокійні акценти, чітка типографіка й контраст без neon |

Джерела UX-аудиту: `warehouse/frontend/src/control/main.tsx`, `CompanyPreview.tsx`,
`SecuritySettings.tsx`, `api.ts`, `style.css`. Це висновки з implementation structure,
не вигаданий usability-test реальних користувачів. Старі успішні browser tests
зберігають історичний статус; їх не повторювали в цій фазі.

## 2. Інформаційна архітектура

- Огляд клієнтів: scope, бізнес-показники, next actions, винятки, короткий source health.
- Клієнти: усі / потребують уваги; пошук, фільтри, сортування, пагінація.
- Профіль: Огляд / Продукти / Працівники / Фінанси / Активність / Нотатки / Історія.
- Робоча черга: пов'язана з клієнтом конкретна дія, відповідальний, строк, терміновість, статус.
- Екосистема: Warehouse доступний; Telegram/Garage, Sites, Billing, referrals — План,
  не активні фальшиві сторінки. Наявність фінансового read adapter не доводить його
  operational readiness чи повноти метрик.
- Безпека та налаштування: власний доступ, тема; політика входу з сервера.

Стабільний глобальний directory profile має набір namespaced SourceLink і продуктних
workspace identities. Наявний Warehouse workspace не автоматично дорівнює людині,
юридичній особі або Billing account. Складні cross-product identity merges не входять
у UI-пакет. Нові адаптери надалі під'єднуються до існуючого BFF/projection підходу,
із явними environment, freshness, capability і coverage; не через fan-out кожної таблиці.

## 3. П'ять узгоджених макетів

1. `#/overview`: 4 компактні KPI, активність компаній, фокус менеджера, винятки.
2. `#/clients`: 8 колонок, живий mock-пошук, status/manager filters, sort, 2 сторінки.
3. `#/company/1`: повний профіль і 7 доступних розділів; 34/10 пояснено як квотні
   одиниці, не всі авто. Реальний клієнт зі скриншота не відтворюється.
4. `#/queue`: строки, пріоритети, зміна demo-status, створення локального завдання.
5. `mobile.html`: те саме workspace на 390 px; 320/768 також перевіряються. Клієнти
   і завдання перетворюються на картки; вкладки профілю мають локальний scroll.

Усі маршрути взаємопов'язані. Themes: Light, Onyx, Midnight Gold, Forest Slate.
Роль «Підтримка» у макеті маскує контакт і не відкриває фінансову вкладку. Це демонстрація
політики, а не frontend-реалізація security: реальний backend повинен залишитися
остаточним джерелом RBAC. Власник бачить honest unavailable state фінансів, а не нулі.

Вигадані 12 компаній у макеті **не є** 5 реальними staging-компаніями. Імена синтетичні,
email у reserved `.invalid`. Денний графік stock operations із концепції 01 вилучено під час Review 02: чинний API не повертає серії. За цими
числами не можна робити висновки про клієнтів, виручку чи реальні понадлімітні дані.

## 4. Компоненти та залежності

```text
GlobalCrmShell
 ├─ ConceptBanner / EnvironmentScope
 ├─ Sidebar → NavGroup (smooth open / immediate close)
 ├─ WorkspaceHeader → Breadcrumbs / ThemeSwitch / StaffContext
 └─ RouteOutlet
     ├─ Overview → MetricCard / BusinessActivitySummary / AttentionList / SourceHealth
     ├─ ClientDirectory → FilterBar / ClientTable / ClientCard / CursorPagination
     ├─ CompanyProfile → ProfileHeader / ProductAccessStrip / ProfileTabs
     │   ├─ QuotaUsageCard / ContactOwner / SubscriptionContext
     │   ├─ ProductConnections / TeamTable / PermissionBoundary
     │   └─ ActivityTimeline / InternalNotes / AuditHistory
     ├─ WorkQueue → WorkFilters / TaskTable / TaskCard / TaskComposer
     └─ SecuritySettings → PasswordChange / SessionPolicy
```

Спільні primitives: Badge, Button, EmptyState, ErrorState, LoadingSkeleton, Dialog,
FormField, Tooltip, Timestamp, Avatar. Зберегти теми й доступність наявних компонентів.
Source health у detail, без технічних DSN/schema/cursor у бізнес-навігації.

## 5. Реалізація одним пакетом ПІСЛЯ погодження

1. Зафіксувати затверджені screen hierarchy, терміни статусів, scope business activity
   і semantic tokens. Прийняти умови мінімальних backend доповнень нижче.
2. Додати маршрути `/control/clients`, `/control/clients/:id/:section`, `/control/work`,
   оновити shell і breadcrumbs. Зберегти current session API/CSRF/Origin/flags.
3. Перевикористати чинні company/people/usage/notes/tasks API та projection, без нової CRM
   DB і без зміни financial/quota policy. UI не має списуватися з синтетичних даних.
4. Зробити таблицю й мобільні картки, enum filters і URL-bound view state; серверну
   cursor pagination зберегти. Додати лише погоджені server sort fields, якщо потрібні.
5. Профіль: незалежні data sections і permissions. Notes/history/status changes лише
   через чинні scoped API; без cross-company leakage або нових повідомлень клієнтам.
6. Огляд: existing workspaces/new_30d/states/tasks можна використати з коректними
   назвами. Бізнес-активні компанії за 7 днів потребують scoped aggregate над projection,
   не підрахунку завантаженої сторінки. Денний графік потребує окремої source series;
   до її погодження показувати чесний summary, а не вигаданий графік чи fake trend.
7. Список продуктів наразі Warehouse; інші capabilities disabled. Фінанси — перевірка
   дозволу і provenance до показу. Не додавати доходи/paid-count до затвердження методології.
8. Черга: чинні due/status/assignee. Перший пріоритет можна виводити зі строку/ризику
   без міграції; ручний priority або делегування новим assignee потребують окремого
   погодження контракту/прав. Не змінювати схему «для майбутнього».
9. Цільові component/browser tests нового shell, routes, keyboard/focus, filters/cursor,
   перехід row→profile→task, stale/unknown/partial/error, permissions та 4 теми / mobile.
   Повний Warehouse прогін лише при відповідних domain changes або новому ризику.
10. Один reviewable PR-пакет з rollback попереднього UI. Окремий дозволений staging
    rollout після review; не вважати це завдання дозволом на deploy чи merge.

Неминучі data gaps для погодження: quota breakdown конкретного workspace; scoped
business-activity aggregates; достовірне payment evidence; filtered aggregate counts;
повноцінна історія компанії (поточний audit endpoint має власний RBAC і може містити
інші staff events, його не можна просто показати всім). Це вузькі read-model/contract
доповнення лише після review, не переписування Backend.

## Критерії приймання наступного пакета

Немає зміни тарифних формул, прав, записів і інтеграцій без дозволу. UNKNOWN не
перетворюється у FREE; trial/grace не стають оплатою. Ліміт не плутається із загальним
архівом; login не стає business activity. Немає фальшивих модулів, доходів чи global
counts із першої сторінки. Доступність: keyboard/visible focus/ESC/return focus,
контраст тем, reduced motion, кероване меню, відсутність document overflow на 320 px.
