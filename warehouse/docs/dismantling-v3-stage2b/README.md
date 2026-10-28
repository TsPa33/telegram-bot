# Warehouse v3 — Stage 2B: керований план розбору

Продовження `9ab958adc01437bf32e4f5212a48aa3ea3c8b0bd`. Робота локальна, лише `/warehouse`. Stage 1/1.5/2A, Global Catalogue v2, основний Telegram-бот та механізм дедуплікації імпортера збережені. Push/deployment/staging apply/production не виконуються.

## Схема збереження

Використовується **чинний DismantlingItem**, а не інша система складського обліку:

- `vehicles.dismantling_v3 JSON`: ревізія прийнятого плану, версія, базові engineering SHA, ID використаної підтвердженої конфігурації, snapshot/revision каталогу, збережені пробні facts/selected, причини пропуску кандидатів і прийнятий preview token.
- `dismantling_items.plan_v3 JSON`: canonical_part_type_id, placement_id, snapshot кандидата/варіантів/доказів/довідкових цін, inspection, reason, причина ручного зіставлення та ревізія.
- Існуючі `included`, `status`, `quantity`, `part_id`, `received_at`, source/catalog_key залишаються чинними. При зв’язуванні legacy не змінюються ID, source/catalog_key, Part, ціна, кількість, operational status чи попереднє included.
- `dismantling_requests`: тільки durable replay protection для команд. Unique `(account_id, request_key)`, vehicle/actor, SHA нормалізованого запиту, компактний результат. Це не складський ledger і не копія позицій.
- Аудит — існуючі **Operation**, append подій `dismantling_v3_bind`, `dismantling_v3_save`, `dismantling_v3_decision`; before/after та actor_identity з серверної сесії. Старі записи аудиту не переписуються.

Additive migration `84d2c6fa190b` від `76af12de4b90`: дві JSON-колонки з порожнім object default, replay-таблиця та partial unique index `(vehicle_id, plan_v3 ->> 'placement_id')`. Єдина head. Немає startup backfill або створення планів. PostgreSQL default робить старі рядки доступними з порожніми метаданими; історичні business-поля залишаються незмінними.

**Downgrade після використання v3 видаляє нові метадані/ключі replay.** Це не процедура збереження рішень. Перед будь-яким майбутнім release потрібен backup та перевірений restore; автоматичного downgrade/deployment цей етап не виконує.

## Preview → підтвердження → atomic save

Маршрути:

- `GET /api/v1/vehicles/{id}/dismantling-v3`: тільки читання збереженого плану, summary, etag, ознаки stale configuration/catalogue. Немає генерації або prepare.
- `POST .../preview`: тільки обчислення. Існуючі ConfigurationPreview facts/selected + `resolutions` та `reset_trial:false`. Генератор Stage 2A перевикористовується; план/preview-ticket у БД не створюється.
- `POST .../save`: ті самі вхідні дані, `token`, UUID `request_key`, `confirm:true`. Показує proposed/existing/new/legacy_possible/unverified/stock_history/review/skipped до підтвердження.
- `POST .../decisions`: IDs, action, etag, UUID request_key, reason; для dismantled/receipt обов’язкове confirm:true.

Token — SHA серверного preview, прив’язаний до actor/session, engineering/конфігурації, всіх входів, каталогу, плану та stock/audit etag. Клієнтські рядки snapshot не приймаються як authoritative. Save повторно обчислює preview з фактичних джерел під vehicle row lock і global catalogue advisory lock. Якщо каталог зайнятий, **409 без очікування довгого імпорту**, без запису. Застарілі/невирішені зіставлення дають 409. Усі рядки, метадані, аудит і replay result commit-яться однією транзакцією.

Повтор успішного UUID + того самого actor/payload повертає durable результат навіть після перезапуску. Інший payload/vehicle/actor із тим самим ключем дає 409. Авторизація завжди перевіряється заново. Паралельні зміни одного донора серіалізовані vehicle lock; stale etag блокує overwrite. До commit аварія відкочує весь пакет; після commit втрата HTTP-відповіді безпечно відновлюється тим самим ключем. Немає background save або автоматичного retry/apply.

## Зіставлення з legacy і запобігання дублям

1. Існуюче точне placement_id зв’язується зі своїм DismantlingItem.
2. Для legacy використовуються вихідні посилання та вже перевірена нормалізація функції/сторони/позиції/mount/ordinal. Один точний безальтернативний збіг можна повторно використати.
3. Широкі/уточнені позиції, кілька старих рядків, невизначені назви в тому самому контексті — **review**. Також review для можливої загальної/уточненої фізичної позиції серед нових кандидатів.
4. Ручне рішення: `link` тільки до власного допустимого рядка, `new` як явне підтвердження окремої конструктивної позиції, або `skip`; причина обов’язкова. Один рядок не можна одночасно прив’язати до двох позицій.
5. Явне уточнення вже зв’язаного загального рядка можливе через skip старого кандидата + link уточненого до того самого row ID. Рішення/receipt/Part зберігаються, зміна mapping аудитується. Це не автоматичний rebind.
6. Пропуски кандидатів із причинами зберігаються в header; наступне оновлення їх не скидає. Історичні рядки, яких більше немає в поточному preview, залишаються у плані.
7. Existing legacy duplicates не видаляються «очищенням»; preview дозволяє вибрати один рядок, решта залишаються історичними. Не створюються приховані нові дублікати.

Partial unique index захищає поточну canonical placement-прив’язку, а unique source/catalog_key та durable replay залишаються додатковими гарантіями. Новий фізичний row/source key враховує creation request: явне створення окремого рядка після ручного refinement не повторно використовує історичний legacy key. Ідентичність збереженого рядка стабільна при наступних оновленнях.

## Три незалежні стани

| Поняття | Значення / джерело |
|---|---|
| Застосовність | confirmed / possible / unknown / incompatible із прийнятого snapshot Stage 2A |
| Перевірка власника | unchecked / present / absent / not_applicable у plan_v3 |
| Операційний стан | not_dismantled / dismantled / received / sold із чинних status, receipt marker, Part та Operation |

Present **не** створює Part або quantity на складі. Dismantled змінює лише старий workflow status. Receipt — окреме підтвердження, вимагає included + present + dismantled, quantity та stock RBAC. Використовує існуючий `dismantling.receipt` → Part/Operation. selling_price у новій команді не приймається і не береться з каталогу; продажних цін/фінансів планові команди не змінюють.

Звичайний unknown кандидат може бути в плані як unchecked, але не може автоматично оприбутковуватися. Власник може фізично підтвердити наявність навіть тоді, коли довідник сумнівається; це не змінює глобальний fitment.

Sold позначається лише коли складський залишок нульовий, історія підтверджує достатній продаж і немає іншого списання/зменшення, яке зробило б висновок неоднозначним. За змішаних рухів консервативно залишається received; деталі руху — в існуючому складі. Received/count у плані означає факт історичного надходження, не обіцянку поточного залишку.

## Виключення, повернення і захист історії

- absent/not_applicable вимагають reason та ставлять included=false, не змінюючи глобальну застосовність.
- exclude вимагає reason і змінює included; не видаляє рядок або Part.
- restore повертає included; absent/not_applicable повертаються в unchecked, щоб попередня відсутність не стала автоматичною наявністю.
- Категорія/пошук/стан фільтрують таблицю; масова дія над явно вибраними IDs. До 1000 рядків за запит, без прихованого часткового commit.
- Будь-який part_id/received_at захищає рядок від простого виключення, включно з receipt/sale/reservation/write-off history. Блокування одного рядка скасовує весь пакет.
- Старі plan/status endpoints не дозволяють обійти причини/наявність/демонтаж v3. Shared receipt guard діє і для старого add-stock маршруту. Durable received_at запобігає другому надходженню, навіть коли залишок уже продано.
- Legacy prepare після активації v3 не додає другий базовий каталог.

## Зміна конфігурації та каталогу

Прийняті trial facts зберігаються для наступного перегляду каталогу й між сесіями, завжди reported. Форма після reload не скидає їх до unknown через порожні inputs. `reset_trial:true` явно відкидає старі trial facts; UI має окремий checkbox.

Якщо Vehicle engineering або reviewed VehicleConfiguration змінилися, старі trial facts вимагають нового review; preview бере актуальні джерела та показує configuration_changes, але збережений план не оновлюється до confirm. Підміна trial confidence не створює confirmed.

«Перевірити оновлення каталогу» обчислює нові позиції, нові variant IDs/OEM, зміни довідкових цін/застосовності, можливі конфлікти, retained historical rows і старі owner decisions. Зберігаються snapshot та revision Global Catalogue, щоб бачити і source price updates, і нову normalization publication. Імпорт BMW/Audi/Volvo сам не змінює плани. Нерозпізнані джерела не означають непридатність.

## UI

Один основний список: збережений план **або** preview різниці **або** read-only Stage 2A. Старий робочий список відкривається окремо і не показується одночасно. Автоматичного `/prepare` при відкритті немає.

Summary: позиції, possible/unknown, present, excluded, received; категорії/підкатегорії, пошук, фільтри, вибір показаних рядків. На iPhone таблиця стає компактними картками. Масові дії показуються тільки після вибору, checkbox/кількість/зміна вибору скидають попереднє підтвердження. Present, exclude, dismantle та receipt мають різні підписи/наслідки. Dismantle/receipt мають окреме підтвердження.

Збереження йде після явної дії; мережеві помилки не очищують введення. Повтор команди використовує той самий UUID; «Оновити збережений план» робить лише GET, дозволяючи перевірити невідомий результат без повторного застосування. Після reload читається реальна БД, не запускається жодна команда. Незбережений preview не є збереженим планом.

## Безпека

- GET/preview: vehicles.view + catalog.view, workspace ownership, session/CSRF для POST.
- Save та owner decisions: dismantling.manage.
- Receipt додатково: inventory.create + inventory.adjust_quantity.
- Archived vehicle: читання/preview дозволені, мутації блокуються.
- Admin catalogue/allowlist/aliases/VIN-ready контракт Stage 2A не послаблено. Зовнішній VIN API не інтегровано.
- Replay не надає право виконати дію після втрати permission; actor береться з сесії. UUID чужого workspace не можна використати для binding чи decision.

## Реальний XC90 і обмеження

[Локальний артефакт](xc90-real-A.json): реальний пакет Volvo A через Global Catalogue v2, synthetic donor XC90 2020, пробні petrol/diesel факти непідтверджені. Реальний B не доступний і не тестувався.

168 кандидатів Stage 2A. Fixture **не погоджує неоднозначності**: 35 review-кандидатів явно пропущено з причиною, 133 позиції створено без Part/stock. Наступний дизельний preview повторно використовує 133 ті самі рядки, не створюючи нових. Це демонстрація workflow, а не підтвердження фактичної комплектації конкретного XC90.

Покриття каталогу лишається 15,57%; Stage 2B не вигадує функції для 84,43% нерозпізнаних пропозицій. Ручні legacy/physical ambiguities треба перевіряти, а не масово auto-approve. Великий каталог/план із багатьма історичними snapshots потребує staging performance-перевірки. Цей етап не дозволяє самостійний release чи staging import.

## Локальна перевірка

```bash
cd warehouse/backend
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_catalogue_v2_suite_test python -m pytest -q
python -m alembic heads
# alembic check — тільки на явно заданій локальній *_test DB
cd ../frontend
npm run build
node --test tests/*unit.mjs
# API 8014 на окремій warehouse_stage2b_browser_test DB + production assets:
WAREHOUSE_API_PROXY=http://127.0.0.1:8014 npm run preview -- --host 127.0.0.1 --port 5182
WAREHOUSE_E2E=1 node tests/managed-dismantling-browser.mjs
WAREHOUSE_PREVIEW_ORIGIN=http://127.0.0.1:5182 WAREHOUSE_E2E=1 node tests/dismantling-preview-browser.mjs
```

DB-тести стирають лише disposable test DB. Browser-сценарій явно оприбутковує synthetic generator у власній локальній тестовій БД — не staging/production. Логи/скріншоти: `/workspace/scratch/stage2b-*`.

## Результати перевірок

- Повний backend: **464 passed, 1 skipped**, 424,59 с; skip — opt-in benchmark.
- Фінальний цільовий набір керованого плану + populated Team migration: **18 passed**, 96,75 с.
- Після консервативного уточнення incomplete legacy sale evidence: **3 passed**, 3,47 с (неповна історія, повний state/receipt/sold flow, persistence trial facts). Ці набори перекриваються, їх не підсумовують.
- Шість окремих populated downgrade/upgrade regression перевірок пройшли; єдина head **84d2c6fa190b**, `alembic check`: **No new upgrade operations detected**.
- Frontend: **349 unit tests passed**, TypeScript/Vite build успішний.
- Browser 1440px та 390px: managed workflow **PASS**, Stage 2A read-only regression **PASS**. Перевірені втрачена save-відповідь і повтор того самого UUID, захист double-click, category exclusion/restore/reload, presence → dismantled → explicit receipt, блокування виключення stock history, відсутність автоматичного prepare/start/add-stock. Зміна receipt quantity скидає попередній confirm.
- Ін’єкція помилки посеред плану та другого receipt відкочує весь пакет, включно з Part, category, Operation і replay.
- Перевірені same-model donors, cross-workspace/permissions, archive, source updates, зміна двигуна, збереження/скидання trial facts, concurrent commands, stale token/etag, неоднозначні/уточнені legacy bindings, збереження виключень, старих цін, резервів і продажів.
- `git diff --check` без помилок; файли тільки `/warehouse`.

## Залишкові ризики перед окремо дозволеним staging release

1. Потрібні backup/restore staging-БД, звірення фактичного revision та застосування **лише schema migration**; цей етап нічого не публікує і не імпортує на staging. Нових Railway Variables для workflow немає.
2. Реальний B не перевірено. Реальний A має низьке перевірене покриття; 133 збережені fixture-позиції не є підтвердженим повним комплектом XC90.
3. Старі дублікати/нерозпізнані legacy рядки залишаються історичними й вимагають ручного зіставлення. Незв’язані вручну створені Part не зливаються за назвою/OEM: перед receipt потрібна фізична перевірка тотожності.
4. Великі legacy-плани, snapshots та bulk receipt треба профілювати на ізольованому staging; поточний main UI читає збережений план цілком. API обмежує mutation batch 1000 позиціями.
5. Відсутні зовнішній VIN/build-sheet provider та автоматичне підтвердження заводської комплектації. Unknown ніколи не означає «немає».
