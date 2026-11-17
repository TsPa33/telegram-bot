# Фінальний UX/UI Review 02

17 листопада 2026, Київ. База: `36abc441e934fe4a89e6135a98a83279828a2bbe`.
Статус: **пакет готовий до погодження власником; у робочу CRM не інтегровано**.

## Що виправлено

| Область | Знайдений недолік | Остаточне рішення |
| --- | --- | --- |
| Усі екрани | Дрібні 9–10 px підписи, нерівномірні controls | Основний текст 12–13 px; більші metadata, спільна висота controls; великі mobile targets |
| Контраст | Межі input/select губилися на surface | Окремий control-border token; перевірка контрасту всіх чотирьох тем |
| Семантичні кольори | У Gold/Forest «чинний» і попередження могли бути однаково золотими | Success palette відокремлена від brand accent; warning і danger мають власний сенс і текст |
| Огляд | Денний графік і count за 7 днів не забезпечені чинним API | Остання відома бізнес-активність компаній; жодної вигаданої часової серії |
| KPI | Aggregate «потребують уваги» потребує додаткового scoped read-model | KPI завершених періодів із існуючих states; attention view залишається явно погоджуваним read-model extension |
| Список | 8 колонок створювали зайве прокручування на tablet | Фіксовані частки ширини, wrap, прибрані зайві avatar у таблиці; адаптивні картки на вузьких екранах |
| Клік клієнта | Працювало лише посилання на назві | Весь рядок відкриває профіль; native primary link збережено для Tab/Enter/new tab |
| Фільтри | Attention-подання не було узгоджене з URL та active menu | Hash-bound attention state, правильний активний пункт і батьківський розділ |
| Сортування | Mock мав activity-sort, якого не підтримує чинний endpoint | Name/registered працюють; activity-sort disabled «згодом» до погодження контракту |
| Профіль | Повторення контактів, plan/status і quota у кількох секціях | Контакти в header, менеджер/контекст окремо, ліміти тільки в Overview; Products посилається на них |
| Профіль | Raw status можна було прийняти за повний операційний доступ | Тарифний стан, операційний доступ і payment evidence розділені; неперевірений доступ не видається за дозволений |
| Активність/Історія | Demo-події створювали враження вже підключеної повної стрічки | Час останньої операції; повна історія і детальна стрічка мають чесний unavailable state |
| Черга | Priority не узгоджувався зі строком; після status update губився focus | Терміновість виводиться зі строку; мінімум кольорів; focus відновлюється на task control або поточному фільтрі |
| Пагінація | Після зміни сторінки DOM replacement губив focus | Focus на активній сторінці після paging |
| Sidebar | Закритий off-canvas залишався в keyboard-порядку; не було focus trap | Inert закритого drawer, modal focus containment, ESC/close/scrim і повернення focus; адаптація вже на tablet |
| Анімація | Перехід до mobile міг показати проміжний кадр закриття sidebar | Плавне відкриття, миттєве закриття; reduced-motion без анімації |
| Mobile | People-table не мала card variant | Компанії, працівники й завдання використовують спільні дані та адаптивні картки |

## П'ять екранів: фінальна оцінка

**Головний огляд.** Послідовність: scope → чотири KPI → остання бізнес-активність і
завдання → короткий unavailable фінансовий контекст → конкретні клієнти для перевірки.
Немає великого порожнього revenue-блока чи штучного графіка. Основні дії доступні
в header, task list і row navigation. Логін не прирівнюється до складської активності.

**Список клієнтів.** Пошук, status/manager filters і sort в одній панелі, paging під
списком. Тарифний стан названо саме тарифним, не «оплачено». Контакт, продукт,
реєстрація, бізнес-активність і відповідальний залишилися. Таблиця компактна на desktop;
на tablet/mobile — картки без приховування потрібних полів. Помітний primary link
доступний із клавіатури, рядок розширює mouse hit area.

**Профіль.** Контакт у короткому header, одна смуга тарифного стану / перевіреності
операційного доступу / тарифу / оплати, сім route-based вкладок. Квота 34/10 має
пояснення occupied donors і текстове перевищення, а не легенду «всі авто». Контакти
й квота не дублюються у сусідніх картках. Повна сторінка замість широкого modal.
Unknown/unavailable дані не замінені нулями. Role preview зберігає колишню демонстрацію
прихованих фінансів, не змінює реальні права або backend authorization.

**Робоча черга.** Дія веде прямо до клієнта. Строк, assignee, status і похідна
терміновість утворюють спокійну ієрархію; кольори не замінюють текст. New Task має
компактний native dialog. Зміни існують лише в пам'яті prototype. Після дії можна
продовжити роботу клавіатурою без повернення на початок сторінки.

**Mobile.** Ті самі fixtures, routes й renderer, без окремої мобільної бізнес-логіки.
Sidebar переходить у drawer вже на tablet. На 320/390 основні controls мають 44 px
цілі, профільні вкладки — 46 px; таблиці замінюються картками. Local horizontal scroll
залишено лише для смуги семи вкладок, не для сторінки або client directory.

## Перевірки та межі доказів

- Chromium + WebKit × Light/Onyx/Midnight Gold/Forest Slate × 320/390/768/1440:
  **32 конфігурації / 160 основних screen checks**.
- Додатково всі сім вкладок профілю: **224 section checks**.
- **8 interaction scenarios**: row/card navigation, filters/empty/paging, active nav,
  unsupported sort, notes escaping/isolation, task compose/status, keyboard/native
  links, drawer focus containment/ESC/inert/return focus.
- Перевіряються document overflow, desktop-table overflow, закритий drawer, JS errors
  та відсутність зовнішніх запитів. Новий preview не робить API/CRM calls.
- Контраст основних token pairs: текст ≥4.5:1, controls ≥3:1. Light muted/subtle
  4.58:1, Light control/surface 3.64:1. Успішний token є окремим від brand accent.
  Це цільовий вимір семантичної палітри, не повний WCAG-аудит усіх можливих станів.
- 38 PNG: 32 desktop/mobile у чотирьох темах + п'ять ключових зображень і Forest overview.
- Самодостатній file:// HTML перевіряється в обох engines. Артефакти позначені як
  synthetic review; жодних реальних контаків, паролів або фінансових сум.

Receipts: `verification/review-02-matrix.json`, `review-02-interactions.json`,
`review-02-offline.json`. Попередні auth/backend/повний Warehouse тести не запускалися.

## Основа API для майбутнього впровадження

| Елемент | Чинне джерело / межа |
| --- | --- |
| Клієнти, власник, працівники, plan/status/usage | scoped `/companies` та `/companies/:id` |
| KPI workspaces/new_30d/states | `/overview`, у межах staff scope |
| Остання бізнес-активність | business_activity_at з company snapshot; без історії деталей |
| Реєстрація, name/registered sorting, cursor | чинний directory API |
| Нотатки, assignee, due/status, tasks | чинні scoped endpoints; зберегти RBAC і CSRF |
| Attention view як загальна server-filtered вибірка | окремо погодити вузький filter/aggregate contract, не рахувати поточну сторінку |
| Activity sort, daily series, 7-day global count | не активувати до scoped API-контракту; графік вилучено |
| Операційний доступ | per-operation policy не еквівалентна тарифному status; неперевірено показано явно |
| Історія конкретного клієнта | потрібна scoped history projection; staff audit не показувати всім |
| Оплата/дохід/paid-count | лише verified finance source + дозволи + узгоджена методологія |

## Компоненти, готові як дизайн-специфікації

GlobalCrmShell, Sidebar/NavGroup/ModalDrawer, RouteHeader/Breadcrumbs, ThemeTokens,
MetricCard, LastBusinessActivityList, AttentionList, ClientFilterBar, ClientTable,
ClientCard, CursorPagination, CompanyProfileHeader, PlanAccessEvidenceStrip,
ProfileSectionNavigation, QuotaUsageCard, TeamTable/TeamCard, ProductConnections,
UnavailableState, InternalNotes, TaskTable/TaskCard, TaskComposer, DuePriority,
FocusRestore, SourceFreshnessLabel, PermissionBoundary.

«Готові» означає узгоджений visual/interaction contract для реалізації на наявному
React stack; prototype JS/CSS не слід механічно копіювати у production. Зберегти
наявні shared primitives й серверні security rules.

## Один пакет після окремого погодження

1. Зафіксувати затверджені screenshots, semantics і tokens; scope доступних API.
2. Shell/routes/theme mapping і accessible drawer; без заміни авторизації.
3. Directory + pagination/filter state + row/card navigation, existing backend contracts.
4. Повний профіль із сімома секціями та незалежними loading/error/unavailable states.
5. Queue/composer/status/derived urgency; без зайвої DB-колонки priority.
6. Огляд на чинних полях; вузькі scoped filters/history лише якщо окремо погоджені.
7. Targeted component/browser/RBAC/accessibility checks, один reviewable пакет.
8. Окреме рішення про staging deployment після review. Немає merge/deploy у цій задачі.

Зупинитися на представленні дизайну власнику. Production/БД/тарифи/реальні фінанси,
авторизація та права не змінювалися. Інтеграцію Telegram/Sites/Billing не розпочато.
