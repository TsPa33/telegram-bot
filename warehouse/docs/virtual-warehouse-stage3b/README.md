# Stage 3B — віртуальний розбір в один клік

Основа: `f59eaf93c06247013c6e7bf37dfd6887df94b44f`, гілка `feature/carpot-warehouse-mvp`. Зміни лише в Warehouse. Реалізація використовує **Part + Operation**, не окрему систему залишків.

## Поведінка

«Розібрати авто на запчастини» — одна явна авторизована команда. Вона використовує чинні Stage 2D candidate/partial-plan правила, відкладання цілих неоднозначних груп, exact legacy links і попередні skip/link/new рішення. Безпечні включені позиції отримують Part у звичайному складі. Pending зберігається окремо й не блокує решту.

Новий Part: q=1, reserved=0, enabled=true, location_kind=on_vehicle, quantity_basis=assumed, condition=unknown, OEM/article порожні, selling_price/unit_cost NULL. Кількість 1 — облікове припущення для позиції/лоту, **не** перевірена заводська кількість. Кількість оголошень не використовується як кількість деталей. Відомі окремі placement/сторони залишаються окремими позиціями; невідомі сторони/множинність не вигадуються. Лот із кількома одиницями можна явно відкоригувати; переміщення на полицю стосується всього лота, partial split поки не реалізований.

Part і DismantlingItem не отримують фіктивних received_at/dismantled або фізичного підтвердження від activation. `virtual_activation` змінює тільки облікову кількість, через той самий inventory service та Operation ledger. Походження (snapshot/placement/configuration/request key/quantity basis) зберігається в after.virtual і plan metadata. Part.activation_operation_id посилається на цю єдину подію. Доходи, витрати і receipts не створюються.

«Оновити список» повторно використовує той самий захищений endpoint і актуальні правила/параметри. Додає тільки нові безконфліктні позиції, ніколи не встановлює q=1 для вже пов'язаного Part. Продаж, списання, корекція, архів, резерв, ціна та виключення зберігаються. Потенційна несумісність показується без видалення історії. Уточнення двигуна/КПП зберігаються через чинний редактор, додатковий вибір силової установки застосовується явним оновленням; VIN decoder не додавався.

### Базовий режим і межі Stage 3A

Нове завдання явно дозволяє базовий перелік без розширеного імпорту. Тому нова virtual-команда допускає unpublished snapshot із **наявними** base + constructive inputs і повідомленням про неповне покриття. Це уточнення до Stage 3A, де основна canonical activation пропонувала 409 для unpublished та окремий manual/base шлях. Старий `/quick` і старий preview зберігають колишню поведінку; global catalogue не публікується/не змінюється. Каталог без релевантних джерельних пропозицій також позначено базовим, не повним VIN-каталогом.

Існуючий legacy-план не активується від GET/startup/deployment. Перехід виконується тільки основною кнопкою з поясненням, що включені однозначні старі позиції без Part отримають віртуальний облік. Старі Part повторно використовуються без delta; старі виключення не скидаються. Якщо старе виключення пов'язане з активним резервом, перехід відхиляється до його узгодження. Нові події аудиту додаються лише за явною командою; старі Operation не змінюються.

## БД і міграція

Нова єдина head: **95c3e7b12a04**, down_revision: **84d2c6fa190b**.

- Part: assortment_enabled, inventory_origin, quantity_basis, physical_location_kind, nullable canonical_placement_id, nullable unique activation_operation_id. Defaults для старих рядків — enabled=true, legacy/legacy/unknown; кількості не змінюються.
- Нові CHECK для origin/basis/location, condition допускає unknown без переписування old used.
- Partial unique account+vehicle+canonical placement; FK на canonical placement, operation. Для unpublished template placement зберігається в унікальному DismantlingItem.plan_v3 та provenance; FK Part nullable, бо глобальний unpublished placement не записується автоматично.
- `ck_dismantling_receipt_link` тепер `received_at IS NULL OR part_id IS NOT NULL`: дозволяє Part без фізичного receipt. Unique part_id збережено; доданий і validated composite FK part_id+account_id.
- Нових таблиць товарних залишків немає. Немає migration backfill, activation або імпорту.
- Downgrade має захисний read-only precheck. Без використання virtual metadata/зв'язків можна перевірити legacy roundtrip; якщо virtual inventory використовується або metadata/unknown condition несумісні зі старою схемою — downgrade заборонений. Автоматичний downgrade не запускається. Після activation потрібен reviewed roll-forward, не reset.

`alembic upgrade head` перевіряється повторним запуском; `alembic check` має підтвердити відповідність ORM. Старі regression assertions оновлено до нової head. Старий Smart Search migration failure test порівнює всі поля **старої схеми**, а нові metadata перевіряються Stage 3B тестами; це не послаблення перевірки business data.

## API, права і транзакції

| API | Контракт |
|---|---|
| GET `/api/v1/vehicles/{id}/virtual-dismantling` | Read-only план + stock projection, counts, pending, coverage/etag |
| POST `.../virtual-dismantling/activate` | PlanQuick body: request_key UUID, etag, confirm=true, optional facts/decisions; один atomic commit plan+Part+Operation+audit+replay |
| POST `.../virtual-dismantling/availability` | ids (1..1000 unique), enabled, etag, request_key; atomic вся порція, blocked reservation/zero/archive →409 |

Активація: vehicles.view, catalog.view, dismantling.manage, inventory.create, **inventory.activate_virtual**. Галочки: vehicles.view, inventory.view, inventory.edit, dismantling.manage. Працівникам новий activation permission не видається автоматично; директор має повний workspace-доступ. Це не platform-owner право: global import/publish зберігає незалежну server allowlist, CSRF і перевірку сесії. Немає змін Railway Variables.

Actor/workspace беруться тільки з сесії, не body. Власність Part/Vehicle перевіряється сервером. Account NO KEY UPDATE → Vehicle → Parts — порядок нової команди; спільний owned(Vehicle, lock=True) забезпечує перший workspace lock і старим donor writers. Orders зберігають Account → Order → sorted Parts, а generic Part writers не набувають Vehicle lock у зворотному порядку. Catalogue advisory lock — try-lock, конфлікт дає 409. Зовнішніх запитів у транзакції немає.

DismantlingRequest з новими domain fingerprints забезпечує actor-bound replay. Той самий key/body повертає збережену відповідь **до** stale-etag перевірки. Інший actor/body або новий key зі старим etag →409. Unique placement/Part/activation links доповнюють захист. Втрата HTTP-відповіді не відкочує commit; process death до commit відкочує все.

Браузер зберігає точний payload/key у sessionStorage, scope=actor+workspace+vehicle. Reload не запускає команду автоматично; доступна «Перевірити збережений запит». Невизначений network/server outcome зберігає pending; definitive 4xx прибирає його й оновлює план. Недоступне сховище блокує новий запис із конкретною помилкою. Зміна сесії перевіряється shared API client; stale vehicle response захищено generation counter.

Bulk availability: до 1000 ID на запит, послідовні порції з новим серверним etag. Окрема порція atomic; **весь набір понад 1000 не є однією транзакцією**. Завершені порції залишаються; при перериванні точний pending запит можна повторити, наступний ручний запуск не створює stock delta. Інтерфейс попереджає про цю семантику. Активація плану, на відміну від bulk availability, не розбита на приховані часткові commits і не запускається як BackgroundTasks.

## Три стани й галочки

- q−reserved>0 → «В наявності» з окремими q/available/reserved/sold quantities.
- q>0, q=reserved → «Зарезервована».
- q=0, є достовірні sale quantity snapshots і немає зменшення через write_off/correction → «Продана».
- q=0 без доказів продажу або зі змішаним списанням/корекцією — «Нульовий залишок — див. історію», не фіктивна «Продана». Це history explanation, не четвертий комерційний enum. sold_quantity рахує лише доведені додатні sale deltas.

Checkbox «В асортименті» зберігає доступність, не quantity. Зняти: не видаляє Part/history, не змінює фінанси; r>0 блокує операцію. Повернути: q>0 та не archive, без receipt/+1; q=0 блокує. `included` зв'язаного DismantlingItem синхронізується атомарно. Тимчасове «Виділити для групової дії» — окремий checkbox.

`stock()` централізовано відхиляє новий reserve/sale для виключеного Part, зокрема через Order drafts і старі API; release/cancel не блокуються. Part.quantity/reserved_quantity і чинні OrderReservation лишаються авторитетними. Активні пошуки in_stock, включно Smart Search, не включають disabled Part; history доступна. Фізичний stock q і історія не обнуляються від checkbox. Старий Dismantling receipt для вже virtual Part повертає 409; explicit generic stock receipt залишається окремим фактичним надходженням з власним replay, не кроком генерації.

## Інтерфейс

Один основний VirtualDismantling для картки донора та каталогу у звичайному складі. Одна primary activation; потім secondary update, counts, пошук, category/subcategory cards, availability checkbox, окремий bulk selection. Віртуальні Part одразу доступні у звичайному складі з власною ціною та фізичною локацією.

Картка деталі дозволяє перейти до чинних даних/історії, змінити власну ціну, condition, кількість або перемістити весь лот на полицю з відповідними permissions. Старі масові present/dismantled/receipt кнопки у virtual workflow не показуються. Старий API і named legacy component збережено для сумісності, але не нав'язано основному UI. Pending доступний як згорнутий список причин; повний додатковий редактор manual matching не переносився у новий virtual screen.

Readiness gates Workshop/Team/Smart Search знають нову head і лишають fail-closed для невідомих/паралельних head. Це необхідно, інакше звичайний склад був би заблокований після міграції. Старі сумісні head не видалені.

Повний Price Guidance не реалізований (за актуальним завданням — наступний Stage 3C). reference_prices збережені; жодного автоматичного встановлення selling_price/Aleto copy.

## Перевірки й докази

Повний backend regression: **514 passed, 1 skipped (547.47 s)**; додатковий фінальний Stage 3B набір: **13 passed**. Frontend unit: **379 passed**. Production build, native browser 1440/390 і Alembic check: **PASS**. Пропущено лише opt-in 100k search benchmark.

Підсумкові числові результати записані у [test-results.json](test-results.json). Докази браузера — [browser-results.json](browser-results.json). Тести виконуються лише в окремих loopback PostgreSQL `warehouse_stage3b_test` / `warehouse_stage3b_browser_test`, не staging.

Нові backend-сценарії: Part та Operation activation без receipt; pending; same-key/concurrent replay/stale key; базовий шаблон і GET без записів; checkbox/reserve/sale/zero/partial quantities/transfer; Order reservation consume і disabled draft; зміна силової установки зі збереженою ціною/виключенням; failure після записаних stock events → повний rollback; workspace/CSRF/RBAC/platform-owner isolation; archive; populated upgrade/retry/guarded downgrade; 33-row legacy з 30 receipt histories, sale/archive/prices/cost та виключеннями.

Native Chromium використовує реальний локальний API/PostgreSQL і production build. У synthetic XC60 fixture на кожній ширині: **226 створених Part, 2 pending**, повторне оновлення **0 activation**, bulk exclude/restore всіх 226 (понад перші 60), окремі availability toggles, price/condition editing, звичайний склад і unchanged historical donor. Desktop також втрачає відповідь після server commit, reload і same-key replay. Нові локальні донори створюються для кожного повтору; попередні не очищаються.

**Це не реальний Volvo B.** Seed використовує synthetic reference fixture без canonical publish endpoint. Повний regression набір може читати наявний реальний пакет A; це не доказ тестування B або staging.

| UX | Desktop 1440px | iPhone 390px |
|---|---|---|
| До створення | [screenshot](stage3b-new-1440.png) | [screenshot](stage3b-new-390.png) |
| Готовий розбір | [screenshot](stage3b-ready-1440.png) | [screenshot](stage3b-ready-390.png) |
| Картка | [screenshot](stage3b-cards-1440.png) | [screenshot](stage3b-cards-390.png) |
| Звичайний склад | [screenshot](stage3b-inventory-1440.png) | [screenshot](stage3b-inventory-390.png) |

### Повторити локально

```sh
cd warehouse/backend
# Dedicated disposable DB ONLY; pytest fixtures erase this test database.
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage3b_test python -m pytest -q
python -m alembic heads
# With the dedicated DB URL set:
WAREHOUSE_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage3b_test python -m alembic check
cd ../frontend
node --test tests/*unit.mjs
npm run build
```

Browser bootstrap: створити **нову порожню** local `warehouse_stage3b_browser_test`, застосувати head, на ній один раз `scripts/seed_stage2d_browser.py --confirm-disposable --output /tmp/stage3b-browser-fixture.json` (цей старий bootstrap очищає лише цю порожню disposable DB). Далі тільки `scripts/seed_stage3b_browser.py --confirm-disposable` — він створює нові donors без очищення наявних. API port 8024 з COOKIE_SECURE=false та CATALOGUE_WORKER_ENABLED=false; production frontend preview 5194 з `WAREHOUSE_API_PROXY=http://127.0.0.1:8024`. `WAREHOUSE_E2E=1 node tests/stage3b-browser.mjs`. Значення змінних мають префікс WAREHOUSE_. Не використовувати ці fixture scripts на staging або на локальній БД із потрібними даними.

Готовність: **READY FOR CONTROLLED STAGING RELEASE** після окремого дозволу. Це не підтвердження deployed staging.

## Наступний staging release

Потрібен окремий дозвіл на push/deployment. Перевірити actual remote/fast-forward, Warehouse-only diff, фактичну staging revision та ізоляцію, reviewed upgrade path до 95c3e7b12a04. API startup застосує additive migration під наявним advisory migration lock; він **не** активує донорів, не імпортує й не публікує каталог. API та Web повинні оновитися обидва: старий Web gate нової head не знає, новий Web зі старим API ще не має virtual endpoint — тимчасова fail-closed недоступність під час rollout очікувана.

Після deployment: SUCCESS/health/startup migrations; read-only перевірка global catalogue/Volvo B/canonical snapshot і старого XC60. Потім лише на спеціальному дозволеному test donor/workspace — activation, reserve/sale/exclude/refresh і counts. Не запускати activation/refresh на існуючих користувацьких планах без їхньої явної дії. Не змінювати Railway Variables, не робити reset/backfill/re-import/publish. Для працівників окремо надати новий `inventory.activate_virtual` за рішенням директора; readiness/allowlist production не змінювати.

Обмеження: немає VIN decoder, фізичного split-lot, server background activation queue, нового парсера, auto price guidance чи масового legacy backfill. Великі активації залишаються однією синхронною транзакцією; окремий benchmark десятків тисяч позицій не заявляється. Поточна перевірка UI охоплює сотні позицій, серверний bulk cap 1000 збережено.

[Змінені файли](CHANGED_FILES.md). Local SHA коміту цього звіту: `git log -1 --format=%H -- warehouse/docs/virtual-warehouse-stage3b/README.md` (повний SHA також у фінальній відповіді). Push/deployment/staging mutations не виконувалися.
