# Issue #490 — VIN → план → склад

Аудит 11.11.2026 (Europe/Kyiv), **до виправлень**, branch `feature/assembly-component-inventory`, GitHub/local baseline `be6448a` (fast-forward з `afdc62a`, 12 source-export/coverage комітів). Worktree до аудиту чистий. [Issue #490](https://github.com/TsPa33/telegram-bot/issues/490), handoff власника прочитані. GitHub GraphQL повернув Forbidden; звичайна HTML-сторінка issue доступна HTTP200, готового звіту/коментарів аудиту там немає. Збережено [текст issue](vin-stock-evidence/issue-490.txt). Це виконаний локальний технічний аудит, **не staging acceptance**.

## A. Матриця наскрізного сценарію

Посилання нижче — `warehouse/`, якщо інше не вказано; номери рядків відповідають baseline `be6448a`.

| Етап | Фактичний стан | Доказ / route / обрив |
|---|---|---|
| Введення VIN | Готово локально | `frontend/src/pages/Vehicles.tsx:129` → `VehicleVinQuickAdd.tsx:21`; GET `/vehicles/vin/decode` → `backend/app/api/routes.py:335`. Auth + vehicles.create, без paid API. |
| Декодери / доповнення | Готово локально; live NOT VERIFIED | `services/vin_lookup.py:21–90`: NHTSA → fallback коли бракує IMPORTANT; provenance/conflicts/5-хв cache, 30с negative cache; `vin_freevindecoder.py:76–113`: robots, delay, 4/7с timeout, bounded HTML. EngineModel не стає engine_code. Offline `test_vin2`, `test_vin_normalize`. |
| Ручне уточнення / збереження | Готово локально | `VehicleVinQuickAdd.tsx:27–38`: поля редагуються, checkbox, POST `/vehicles`; `routes.py:311–331`: workspace Account lock, duplicate VIN, стандартні поля + vin_details; NULL migration `08b72c9d4e16`. `test_vin_intake` для обох VIN, duplicate/concurrent/workspace. Тести не є live decoding. |
| VIN → точний source car_id | **Відсутнє для існуючого VIN-донора** | QuickAdd не встановлює `global_selection`; `api/unified_catalogue.py:285–320` вміє вибрати source тільки при створенні ДРУГОГО автомобіля з directory. Старий POST `/{id}/unified-catalogue:48` жорстко Volvo, моделі 13084/37773; новий default UI не викликає його. Автоматичного достовірного VIN→TecDoc car_id немає. Потрібен явний exact-ID вибір користувачем на існуючому донорі, не fuzzy match. |
| Кнопка / потік розбору | Працює частково | `Vehicles:199` → default `ManagedDismantling` → `VirtualDismantling` → default `UnifiedCatalogue:158` → `GlobalCatalogueFlow:35` → `UniversalPlanGenerator:11–12`. Preview + explicit save через чинний `/dismantling-v3/preview`, `/save`. 216 types/227 positions доступні без paid API. Немає вибору source modification після VIN. |
| Exact modification / PRD | Працює частково, data gate | `services/universal_generator.py:45–88`: pinned manufacturer/model/car/SHA/basis; тільки `kind=part` + reviewed taxonomy; exact PRD→canonical reuse лише source ID + source checksum. Без зв'язку/approval чесний baseline; partial не блокується саме через partial. 2184 raw PRD не є runtime types. |
| Універсальний PRD publish | Написано й локально перевірено; runtime НЕ підтверджено | `services/universal_catalogue.py:90–185`, `api/canonical.py:206–222`: existing CanonicalRun preview/publish + platform-admin, worker, locks, checksum, unresolved gate. Правдиве значення approved нових PRD=0. `canonical_catalogue.py` не імпортує MySQL сам. |
| Збереження плану / повтор | Готово локально | `services/dismantling_plan_v3.py:257–283`: DismantlingItem/Operation, stable source/placement, DismantlingRequest replay, ручні рішення/Part/history зберігаються. `test_universal_generator` перевіряє regenerate/replay та історію. Немає автоматичного складу після генерації. |
| Підтвердження фізичної наявності | Працює поштучно; масове написано, але приховане | `AssemblyTree:69`, `assemblies.inspect_item:422`: metadata only; quantity lot correction — через ledger. `dismantling_bulk.py:58` уже підтримує present/dismantled, але компоненти bulk UI імпортуються тільки **LegacyManagedDismantling**, який default wrapper не рендерить. Source-confirmed не означає physically present. |
| Вибрати все / категорію / довільні ID | **Написано, але не підключено до поточного екрану** | `DismantlingBulk.tsx` SelectionCheck/usePlanBulk/BulkActionBar/GuidedReceipt; `/dismantling-v3/selection`, `/bulk/preview`, `/bulk`. Поточний `AssemblyTree` має category/search, але не selection checkboxes. Його «Додати підтверджені» ігнорує видиму категорію й отримує весь donor receipt-preview. |
| Масове надходження | API готове; UX частковий | `assemblies.py:458–502`, `api/assemblies.py:96`: максимум 100, token, all-or-nothing eligible subset, workspace/vehicle locks, durable request key, skip children/already-received/absent. Після 100 наступна порція вручну. `dismantling_bulk` + `bulkDismantling.ts` уже мають checkpoint/progress/retry/100 receipts/1000 metadata actions; не підключені в новому екрані. |
| Ціна / кількість / локація | Написано; доступне у складі, частково приховане при receipt | `DismantlingBulk.tsx:43–53` GuidedReceipt — кількість/стан/локація/необов'язкова UAH ціна по рядках, але default UI не показує. `PartCard.tsx:23–29`, `pages/Inventory.tsx`, SellerPriceEditor, StockLocationFields, InventoryQuantity — чинні складські інструменти. Фото — окремий upload/photo-storage workflow, не функція генерації. |
| OEM / артикули | API є; поточне відображення розірване | `api/unified_catalogue.py:78–268` supplier/OEM/source pinning; LegacyUnifiedCatalogue мав article manager. У `GlobalCatalogueFlow:37–41` таблиця/articles тільки коли assemblyMode===false, але readiness завжди workspace_enabled=true (`api/assemblies.py:28`) для нормального доступу. Отже новий екран ховає цей механізм. Не потрібно переписувати провайдера. |
| Резерви / продажі / архів / історія | Чинні механізми, не переписувати | `inventory.stock:57` викликає `assemblies.stock_guard`; Part/Operation/Order спільні. `dismantling.receipt:90` durable received_at; нуль після sale не дозволяє повторне receipt. `test_dismantling_workspace`: concurrent/replay/rollback/workspace/children. Повний аудит усіх фінансових каналів не повторювався. |
| Staging API/Web/worker/DB | **NOT VERIFIED** | Авторизованого Railway tool/CLI немає. Одна спроба API `/health`: `CONNECT tunnel failed, response 403`; повторів/обходів не було. Deployed SHA, фактична Alembic revision, source bindings, env isolation, worker, CORS/cookie/live browser невідомі. Історичний afdc62a не видано за поточний deployed SHA. |

## B. Поховані функції — повторна реалізація НЕ потрібна

1. `LegacyManagedDismantling` містить select-all/category, usePlanBulk, GuidedReceipt; default wrapper повертає інший екран.
2. `LegacyUnifiedCatalogue` містить article/OEM UI і професійний Plan.Parts, але default повертає GlobalCatalogueFlow. Не вмикати платний старий flow заради mass stock.
3. Фізичний Assembly flag вимикає attach/detach/return, **не базовий склад**: readiness.workspace_enabled=true та inspect/receipt/receipt_bulk доступні без flag. Не потрібно вмикати ASSEMBLY_INVENTORY_ENABLED для VIN→stock.
4. Generic `CatalogueAdapter.directory/plan(global_source=True)` вже працює для різних manufacturer IDs. Volvo-specific legacy selection не треба розширювати списком моделей; повторно використати generic directory validation на існуючому донорі.
5. Ціни, фото, локації, резерви, продажі редагуються в чинному Inventory/PartCard. Не будувати другий stock editor у каталозі.

## C. Блокери та мінімальні diff targets

| Пріоритет | Тип | Проблема / мінімальний патч | Ризик / перевірка |
|---|---|---|---|
| P0 | code | VIN-донор не має generic exact source binding. `api/unified_catalogue.py` + existing `GlobalVehicleForm`/GlobalCatalogueFlow: підтверджений вибір exact source IDs на ТОМУ САМОМУ донорі, без нового Vehicle та без fuzzy VIN inference. | Не міняти VIN/specs/stock; wrong maker/IDs/SHA, retry, чужий workspace, active old plan, unavailable source. |
| P0 | code | Bulk controls відрізані від актуального UI. У `AssemblyTree.tsx` повторно підключити SelectionCheck/usePlanBulk/GuidedReceipt, наявний API для plan selection/preview/execute. | Не робити stock з checkbox. Явні presence/dismantled/receipt; exact selected IDs, category scope, request-key retry та reload. |
| P0 | data | Raw 2184 linked PRD не опубліковані, review=0. Exact source graph ≠ verified Ukrainian type/physical placement. | Спочатку bounded pilot: перевірений snapshot, checksum-bound taxonomy, reviewed part rows; існуючі publish gates не обходити. Не називати усі raw PRD фізичним складом. |
| P0 | environment | Немає авторизованого staging evidence. | Після окремої перевірки env/SHA/HEAD/migrations та login перевірити live E2E. Не може бути оголошено PASS локальними fixtures. |
| P1 | code | OEM/article tools приховані при workspace_enabled=true. | Підключити існуючий article detail у inspector без повернення платного legacy flow. Окремий patch, не переписування provider. |
| P1 | code | У source vehicle_basis не всі VIN2 характеристики; exact binding не можна переобирати поверх історичного плану без explicit reconciliation. | В PR1 нове binding захищати повним identity fingerprint і не замінювати історичний план. Окрема звірка для старих планів; без delete/auto reclassification. |
| P2 | scale/UI | Directory eager-load максимум 100×100=10000; 60098 source modifications у directory ще НЕ імпортовані. Корпоративне UI/UX після функціональності. | Server-filtered lookup до масового наповнення; не робити 60098-option form. Статуси/назви кнопок можна уточнити без redesign. |

## D. Оцінка лише залишку (до PR1)

Не greenfield; наявні VIN/склад/ledger/reserves не входять повторно.

| Залишок | Людино-години | Умови |
|---|---:|---|
| Generic existing-donor source binding + захист historical plan/identity | 2–4 | Чинний Catalogue API доступний; без auto VIN→TecDoc fuzzy resolver |
| Повторне підключення bulk selection/confirmation/GuidedReceipt та progress | 2–4 | Чинний managed plan, збережені request keys, без другого receipt service |
| Targeted API + browser E2E/retry/stock invariants | 2–3 | Локальний isolated PostgreSQL; live QA окремо |
| Авторизоване staging acceptance | 0.5–1.5 | Доступ/ізоляція/deployed SHA надані; очікування доступу не coding hours |
| Разом мінімальний functional pilot | **6.5–12.5** | Не включає data review усіх 2184 чи відсутній зовнішній доступ |
| Повернення article/OEM inspector | 1–2 | Уже є pinned detail API; не scraping/новий provider |
| PR2 корпоративний UI polish | 2–4 | Після PR1 acceptance, без нового design system |

Перевірка 2184 PRD — окрема семантична робота: потрібен сам review CSV/source evidence. Число 122 назв / 42 candidate mappings з handoff НЕ затверджене. Не даємо вигаданий точний строк масового review без файлів. Для планування: 0.5–2 хв/запис означає 18.2–72.8 reviewer-hours, **умовна арифметика, не оцінка виконаного**; синоніми/складні вузли можуть вимагати більше. Pilot 113 не вимагає очікування повного 2184 review, але неоднозначні типи залишаються review.

## E. Мінімальний план двох PR

**PR1 functional:** generic explicit source selection на існуючому VIN Vehicle; та сама універсальна preview/save; увімкнення вже написаних mass selection + presence/dismantled + GuidedReceipt/checkpoints у чинному дереві. API/ledger існуючі. Мінімальні тести нижче. Немає міграцій, paid API, catalogue publish або auto deploy.

**PR2 UI:** компактні corporate states/індикація selection, article inspector, усунення дублювань і відновлення фокуса; лише після functional QA. Не повертати всі legacy екрани й не створювати інший генератор.

## F. Acceptance / фактично перевірено

Baseline offline: **37 PASS** — `test_vin_intake.py`, `test_vin2.py`, `test_vin_normalize.py`, `test_dismantling_workspace.py`, `test_universal_generator.py`; [лог](vin-stock-evidence/baseline-tests.txt). Лише local *_test PostgreSQL, fixtures, не Railway/source. Packaged Alembic head **08b72c9d4e16**, одна; фактична staging revision NOT VERIFIED. Під час read-only аудиту продуктового коду не змінено, local tests виконують DDL/TRUNCATE тільки в окремій тестовій БД, не є операціями з робочими даними.

Обов'язковий PR1 контроль:
- Обидва VIN (YV4L12RK6N1970668 / YV4A22PK2G1092943) у локальних provider fixtures → редагування → один Vehicle → duplicate409. Окремо live декодування у staging після авторизованого доступу, без підміни fixtures.
- Exact car_id107555 + друга марка: звірені source IDs/SHA, існуючий Vehicle не замінено. Не присвоювати будь-якому Volvo VIN цей car_id без ручного підтвердження модифікації.
- Відсутній source → 216/227 загальних кандидатів, без токенів; не показувати 2184/60098 як runtime coverage.
- Категорія → вибрати потрібні → явно present → dismantled → preview кількостей/локації → receipt. Part/Operation тільки після явного receipt.
- Повтор/timeout/reload/новий key після receipt → без другого надходження; більше100 — checkpoint100, кожна порція атомарна; історія попередніх порцій не rollback автоматично.
- Чужий workspace/CSRF/readonly actor — deny; продані/резерви/компоненти не перетворюються на новий товар; старі дані не перезаписуються.

## Джерельні числа та межі доказів

2184 linked PRD, 60098 linked modifications, 67117 scanned, 9378948 unique pairs, 10232 models, 406 maker IDs — **результат локального source-аудиту власника з handoff/issue**, не повторний SQL-аудит у цій сесії, не Warehouse runtime. CSV linked-prd-for-review/by_brand/by_model тут відсутні. Контроль107555: 113 types,736 article refs,175 suppliers,434/436 PDS pairs,0 extra PDS types; manifest `fd66f3cc633f0eb1bb0ad3585bee80b259b2050e4f4ea846745a475551508c8f` — також owner evidence, не імпортований нами.

**Висновок аудиту: базові механізми працюють локально; наскрізний VIN→exact catalogue→scoped bulk stock розірваний у binding/UI; staging і максимальне PRD-наповнення BLOCKED/NOT VERIFIED.** Перш ніж змінювати код, визначено наведений PR1. Окрема секція implementation evidence після патча відрізняє baseline-висновки від виправлень.

## G. Підготовлений локальний PR1 після аудиту

Виконано мінімальні кодові виправлення, **без push/deployment**:

- `api/unified_catalogue.py:362–409`: POST `/{id}/catalogue-selection` на існуючому Vehicle, verified directory/plan exact IDs + snapshot SHA, explicit user confirmation, full VIN2 fingerprint, existing DismantlingRequest replay. Зберігається той самий Vehicle/VIN/vin_details, не створюється другий донор. Додано route registry/RBAC; readonly/CSRF/foreign-workspace deny.
- `universal_generator.py:49`: нові exact bindings стають невизначеними після зміни VIN2 characteristics, drive, engine code та інших identity facts; джерельна асоціація не перетворюється на доведений VIN-fitment.
- `GlobalCatalogueFlow.tsx`: чинний GlobalVehicleForm повторно використано для вибору модифікації на VIN-донорі. Не реалізовано автоматичного вгадування source car_id. «Розібрати на запчастини» використовує той самий UniversalPlanGenerator preview/save.
- `AssemblyTree.tsx`: повторно підключено наявні SelectionCheck, usePlanBulk, BulkActionBar, GuidedReceipt, BulkStatus. Є вибір усіх за фільтром/категорією та довільних рядків, явні presence/dismantled, preview кількостей/стану/локації/необов'язкової ціни, existing checkpoint100/1000/retry. Верхня кнопка при selection передає саме вибрані; без selection явно названа «Додати всі підтверджені автомобіля». Під час receipt preview вибір заморожений.
- Не змінено stock ledger, reservations, sale/finance, source importer, taxonomy, canonical publish, міграції або фізичні AssemblyMembership. Глобальне owner-approved наповнення залишається **0 нових типів**.

### Результати після PR1

| Перевірка | Результат / доказ |
|---|---|
| Targeted backend E2E + existing bulk/physical/generator invariants | **21 PASS** [лог](vin-stock-evidence/vin-stock-pr1-tests.txt) |
| Додаткові нові binding CSRF/actor/stale VIN2/source outage | **2 PASS** [лог](vin-stock-evidence/vin-stock-pr1-security.txt) |
| Frontend checkpoint100/1000, retry, category selection, scope isolation | **9 PASS** [лог](vin-stock-evidence/vin-stock-bulk-unit.txt) |
| TypeScript + Vite build | **PASS** [лог](vin-stock-evidence/vin-stock-pr1-build.txt) |
| Local browser VIN→create→source selection→plan→category→presence/dismantle→receipt→reload | **PASS**, 1440/390, без JS errors/overflow/paid calls [лог](vin-stock-evidence/vin-stock-browser.txt) |
| Real staging/browser/live VIN/provider / actual 113 source data | **NOT VERIFIED**; CONNECT403 та немає авторизованого доступу. Fixtures не є доказом цих даних. |

[Desktop screenshot — synthetic local test](vin-stock-evidence/desktop-1440.png) · [Mobile screenshot — synthetic local test](vin-stock-evidence/mobile-390.png).

Browser harness `backend/tests/vin_stock_browser_server.py` відмовляється працювати поза localhost:55441/*_test і WAREHOUSE_ENV=local/WAREHOUSE_E2E=1; дані явно позначено synthetic. Tests `test_vin_to_stock_handoff.py` перевіряють обидва VIN і Renault з fixture providers, один donor, duplicate VIN409, exact source binding/replay, zero stock before receipt, one Part/one receipt after retry, untouched other category, source outage, forbidden actor/CSRF/workspace, historical-plan preservation. Реальні характеристики цих VIN не встановлювалися заново й не підмінялися fixture результатами у звіті.

### Невиконаний залишок після локального PR1

1. **Джерельні дані/review:** отримати фактичні reviewed pilot snapshots/Catalogue API й перевірити source graph та норми 113/2184. Числа owner audit не опублікували автоматично. Залежність від доступу/CSV; додаткового генератора не потрібно. Точна оцінка семантичного review без цих файлів залишається невизначеною.
2. **Staging acceptance:** 0.5–1.5 години після авторизованого доступу: isolation, actual SHA/head, live VIN і реальний pilot, без paid API. Очікування доступу не включено.
3. **Старі плани:** binding поверх уже існуючого fallback/legacy плану або іншої exact модифікації навмисно409, без delete/merge за назвами. Потрібна явна звірка з чинними preview/resolutions; орієнтовно 1–3 години для pilot з відомими ID, а не автоматична перекласифікація старого складу. Новий чистий VIN flow працює локально.
4. **Article/OEM UI:** P1 лишився, 1–2 години повторного підключення pinned detail у чинному inspector; paid Plan.Parts не вмикався.
5. **PR2 visual polish:** 2–4 години після functional acceptance, не виконувався.

Таким чином, **залишок code/acceptance для pilot без PR2: 2.5–6.5 людино-години**, з яких 1–2 години article inspector можна робити окремо. Data review/отримання source export — окремий блокер, не прихований у «готово». Production та наявні робочі Warehouse дані не змінено. Локальний функціональний PR1 підготовлений; повний live VIN→максимально наповнений каталог→stock **ще не оголошено завершеним**.
