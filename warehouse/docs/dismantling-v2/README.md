# Розбір автомобіля 2.0 — локальне приймання

База9631604d47f6101da6d3afd76209ff158ed339c9, гілка `feature/warehouse-dismantling-v2-ux`. Жодного staging deployment, записів у робочі БД або операцій з автомобілями власника33/34/36. Рік PEUGEOT власника не змінювався. QA — окремі локальні облікові записи й PostgreSQL `_test`.

## Причина та реалізація

227 вибраних неперевірених позицій — не227 фізичних деталей. Старий GuidedReceipt створював рядки лише для receipt-eligible IDs; eligibility вимагала підтверджену наявність. Тому0 до надходження було правильним захистом, але інтерфейс не давав завершити підтвердження в цьому ж сценарії. Додатково великий preview/окреме збереження та порожнє дерево заважали лінійному процесу.

1. Початок: одна головна дія, нейтральна ілюстрація, дані авто. Порожня робоча область/масові дії не монтуються до плану.
2. Підбір: indeterminate progress на час реального preview/save, без таймерів/відсотків/штучного очікування. Захист повторного кліку. Новий план формують і зберігають за явною початковою дією; компактний результат містить фактичні категорії/позиції/уточнення. Наявний план відкривається одразу. Оновлення/неоднозначне зіставлення вимагає контрольованого підтвердження, ручна історія не переписується. Неоднозначні записи можуть залишатися pending_review.
3. Робота: категорії/підкатегорії, список/дерево й наявна картка. Один компактний toolbar вибору; причина запитується при відсутності/виключенні. Фільтри й картка оновлюються без скидання після надходження.
4. Надходження: та сама bulk-команда й inventory ledger. Preview з `confirm_physical:true` лише показує додаткові непідтверджені кандидати. Запис можливий тільки після явного global confirm та per-line `confirm_physical:true`; в одній транзакції фіксуються наявність, демонтаж і звичайний receipt. Невідомі кандидати не додаються від простого checkbox у дереві. Відсутні/виключені/архівовані/продані/вже оприбутковані захищені. Пошкоджений стан зберігається, ціни не копіюються з довідників. Довідкові компоненти не стають SKU.
5. Великі надходження: чинні UI-batches100, pending payload/request_key/checkpoint; підтверджений прогрес, exact replay після невідомого результату, зупинка на зміні etag. Кожна порція атомарна; цілий багатопорційний процес не видається за одну транзакцію.
6. Джерела: новий owner-only GET `/vehicles/{id}/dismantling-v3/sources`, чинний server allowlist `catalogue_import.platform_admin`; DIRECTOR робочого простору не є platform owner. У звичайних plan/assembly/vehicle відповідях технічна provenance мінімізується, але в БД/аудиті зберігається. Кожна позиція потрапляє рівно в один bucket, multi-source має окремий bucket зі збереженням усіх refs; unknown не підміняється вигаданим джерелом.

## Основні файли / API

Frontend: `GlobalCatalogueFlow.tsx`, `UniversalPlanGenerator.tsx`, `AssemblyTree.tsx`, `DismantlingBulk.tsx`, `bulkDismantling.ts`, чинні `universal-generator.css`/`assembly-tree.css`. Нова архітектура/дизайн-система не створювалась.

Backend: `schemas/dismantling_v3.py`, `services/dismantling_bulk.py`, `services/dismantling_plan_v3.py`, `api/dismantling_v3.py`, `api/secure_route.py`, `services/dismantling_access.py`, `route_registry.py`. Preview/save, bulk/preview, bulk, assemblies/split залишаються чинними механізмами. Старі bulk request fingerprints нормалізуються без нових false-полів; cached replay збережено. Нові physical confirmation flags суворо типізовані. Нових міграцій/backfill немає; packaged head08b72c9d4e16.

## Перевірки

- Незалежні150 backend-регресій із чинного workflow +14 bulk/access/regression перевірок: **164 PASS** на `warehouse_dismantling_v2_regression_test`, localhost55441. Конфігурацію pytest не послаблено, проти Railway не запускалося.
- Чинні258 frontend-тестів +12 batch/physical confirmation/checkpoint тестів: **270 PASS**, production build PASS.
- `alembic check`: **No new upgrade operations detected**.
- Нові backend-тести:5 непідтверджених, неправильне підтвердження без запису, кількості, змішаний вибір/пошкодження,227/rollback/replay, concurrency, platform-owner vs director/employee, історичний request fingerprint.
- Існуючий `test_stage2e` узгоджено з уже чинною атомарною поведінкою: present-позиція не потребує окремої дії dismantled перед receipt. Додано третій явно кількісно підтверджений рядок; assertions кількості/історії залишено строгими. Незалежний базовий набір150 не вилучався. Два assertions джерельних лічильників у ньому тепер перевіряють відсутність деталізації для звичайного директора та її доступність лише після server allowlist platform-owner; це новий контракт приватності, а не вилучення перевірок. Порожні масиви provenance зберігають сумісність із попереднім Web.
- Реальний локальний браузер: auth/API/PostgreSQL не замокані. Контрольовано інжектуються503 preview та обрив уже виконаної HTTP-відповіді. Прототипи — окремі ілюстрації, не докази виконаних операцій.

| Browser/SQL сценарій | Фактичний результат |
|---|---|
| PEUGEOT/Renault/Volkswagen, без точної модифікації | По227 потенційних позицій, збереження/reload;0 Parts до фізичного підтвердження |
|5 непідтверджених |5 Parts,7 одиниць після зміни однієї кількості на3;5 receipt operations |
| Змішаний вибір7 |3 нових Parts;2 існуючі лишилися; відсутня/виключена не надійшли; продана лишилася quantity0; пошкодження збережено |
|227 із втраченою другою відповіддю | Після обриву фактично200 Parts, після reload/replay227;227 receipt operations,3 унікальні команди100/100/27 |
| Вузли1/6 | Qty1 guarded split доступний; qty6 заблоковано; reference не створив додаткових Parts |
| Джерела | Director403, platform-owner227 унікальних позицій; employee403 перевірено backend |
| UI | Початок/результат/receipt: day/night1440/1920/390; збережено пошук, категорію та вибрану картку; pageerrors0 |

Логи й скриншоти: `evidence/`. Post-E2E SQL виконується в READ ONLY транзакції лише на dedicated browser `_test`; `sql-invariants.json` підтверджує кількості/operations/унікальні receipt IDs. `tests/dismantling_v2_browser_server.py` — окремий localhost-only тестовий harness, не імпортується звичайним app.main, не працює на Railway/іншій БД. Його synthetic fixture/allowlist не є production endpoints.

## Review / запуск / обмеження

Публікувати лише feature-гілку, Draft PR до `fix/warehouse-502-d-shared-ux`; не main. Deployment у цьому завданні заборонений. Після owner review/незалежного CI окремо погодити встановлення API перед Web (нові receipt flags), перевірити фактичні SHA/health/readiness й авторизований staging QA workspace. Існуючий Web залишається сумісним із default bulk-протоколом; новий Web потребує нового API.

Rollback — application-only; не скасовувати реальні підтверджені receipt SQL/downgrade або видаленням. Перерване надходження продовжувати зі збереженим request key. Не скасовувати невідомий запит іншим записом.

Не реалізовано виділення одиниці з qty6 та новий розподіл собівартості — чинні обмеження збережені. Немає нових платних/зовнішніх API, білінгу, експорту або глобального редизайну. Реальний staging і його дозволи/DB не тестувалися в цій сесії. Візуальне приймання власником ще потрібне. Build advisory про JS chunk і Starlette/httpx deprecation залишаються попередженнями.

Додатковий, поза незалежним CI150, exploratory legacy-прогін: **30 PASS /1 FAIL** (`test_dismantling_preview.py::test_real_A_xc90_read_only_example`). Помилка —409 «Потрібен новий preview» під час підтвердження bundled catalogue fixture, до запуску перевірки preview. Цей самий тест окремо запущено на незміненому9631604… в іншій dedicated `_test` БД: ідентичний FAIL. Це підтверджений baseline-дефект старого fixture/імпорту, не регресія нового надходження; його не приховано і не виправляли розширенням scope. Логи обох прогонів збережено. Чинні150 CI-cases та14 доданих —164 PASS.
