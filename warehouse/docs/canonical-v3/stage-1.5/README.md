# Canonical Catalogue v3 — Stage 1.5

Локальне розширення Stage 1 від `e3871a1`. Основний бот, production і staging не змінюються. Реальний пакет A прогнано через **завантаження/preview/apply Catalogue v2 у одноразовій локальній PostgreSQL**, а потім через canonical preview/publication. Це не staging apply. Реальний B відсутній і не тестувався.

| Метрика реального A | Stage 1 | Stage 1.5 |
|---|---:|---:|
| Унікальні пропозиції | 7 246 | 7 246 |
| Розпізнані пропозиції | 105 | 1 128 |
| Покриття | 1,45% | 15,57% |
| Використані глобальні типи, включно з базовими | 25 | 75 |
| Конструктивні варіанти | 104 | 1 444 |
| Позиції | 38 | 182 |
| Перевірені зіставлення, включно з 33 базовими | 262 | 2 828 |
| Неопрацьовані шляхи | 14 171 | 11 585 |
| Шляхи, що потребують review | 0 | 20 |

Ринкові шляхи окремо: 2 795 перевірених + 11 585 неопрацьованих + 20 review = 14 400. Невирішених загалом **11 605**. Використано 64 типи з ринкового пакета; загальні 75 включають базові. Кількість записів словника (80) не є кількістю фактично використаних типів. Модельні зв’язки пакета: 10 112. Перевірена функція не означає підтверджений fitment.

Артефакти: [реальний A через v2](real-A-validation.json), [30 найбільших невирішених груп](unresolved-A.json), [нові функції та правила](RULES.md). Попередні Stage 1 артефакти залишено для порівняння. Snapshot містить реальні локальні ID, а не ідентифікатори staging.

## Групове погодження — API контракт

Нові маршрути використовують наявні сесії, CSRF і серверну platform-owner allowlist; без allowlist закриті. `catalog.import` або DIRECTOR іншого workspace недостатньо. Actor береться з авторизованої сесії. Існуючі aliases, виведення цін та механізм дедуплікації Catalogue v2 збережені.

1. `GET /api/v1/catalogue/admin/canonical/groups?offset=0&limit=50`: невирішені записи, груповані за запропонованим типом, категорією, підкатегорією, повною нормалізованою фразою і причиною. Пропозиція типу не є погодженням.
2. `POST /api/v1/catalogue/admin/canonical/rules/preview`: `type_id`, `phrase`, `category`, `subcategory`, необов’язкові `manufacturer`/`model`, `conditions`, `expected_revision` (спочатку 0), `evidence`. HTTP 202 повертає durable run; опитувати наявний `GET .../runs/{id}` до done/error.
3. Preview перевіряє **кожний** запис області правила, включно з уже зіставленими: кількість нових/незмінних, винятки, конфлікти, SHA-дайджест усіх відповідностей. Приклади стратифіковані за моделлю, позицією, наявністю OEM і паливом (до 12); винятки та конфлікти також мають загальну кількість і до 12 прикладів.
4. `POST .../rules/approve` з `preview_id`, `token`, `confirm:true`: нова чергова операція повторно перевіряє всі джерела, rules snapshot і revision. Застарілий preview, конфлікт, порожнє правило чи неоднозначна загальна назва блокують погодження. Умови exact/all-of; відсутність ознаки не є збігом. Невідома позиція не обходить вимоги відомого типу.
5. Результат — append-only alias з actor/revision/evidence, попереднім preview та звітом в `canonical_runs`. **Каталог ще не опубліковано.** Після перегляду окремо виконуються звичайні canonical preview і publish з новим токеном. Group-preview не можна використати як токен звичайної публікації.

Це API-механізм; окремий екран групового погодження в цьому етапі не додається. Працює через наявну PostgreSQL-чергу та міжпроцесні блокування. Після аварії unfinished run переходить у контрольовану помилку, повторення тільки явне. Startup не погоджує правила та не публікує каталог. Повторне погодження того самого токена не створює повторного alias: revision/snapshot вже змінилися.

## Застосовність і VIN-ready конфігурація

Read-only candidates отримують `applicability`: A загальна функція, B силова установка, C трансмісія/привід/кузов, D заводські опції, E відсутні підтверджені факти. Варіант має власні вихідні обмеження; групова оцінка є лише оцінкою функції. `condition_met` **не підтверджує fitment**, не виключає позиції та не створює план/залишки. Невідомі рік, точний двигун чи комплектація залишаються невідомими.

Виявлено відсутність попередньої VehicleConfiguration, тому додано сумісний append-only контракт, одну таблицю й additive migration `76af12de4b90` після `5c7d9e1a320f`. Вісім canonical-таблиць Stage 1 перевикористані, не дублюються по workspace. Міграція не містить backfill.

- `GET /api/v1/vehicles/{id}/configuration` — остання підтверджена конфігурація власного workspace або null/stale.
- `POST .../configuration/preview` — `facts:[{field,value,kind,reference,confidence}]`, необов’язковий `selected:{field:factIndex}` для суперечливих джерел.
- Поля: manufacturer/model/generation/year, **engine_code**, fuel_type/powertrain, transmission/drive/body_type, options/options_complete, vin.
- `kind`: manual/document/vin_decode; `confidence`: reported/verified. Відповідь декодера може бути лише reported; для verified потрібне явне ручне/документальне підтвердження. Всі альтернативні джерела збережені; неоднозначність потребує вибору.
- `POST .../configuration/confirm`: preview_id/token/confirm:true. Перевіряє workspace, поточну основу Vehicle й конфлікти; часткова конфігурація допускається, але має missing_or_unverified та complete:false.
- Порожній список опцій не доводить відсутність інших опцій. Повнота потребує окремого verified document факту `options_complete:true`. VIN не декодується автоматично; платних API немає.
- Старі поля Vehicle/плани не оновлюються. Зміна базових інженерних даних робить попередню конфігурацію stale. Права read/edit — чинні `vehicles.view`/`vehicles.edit`, із workspace isolation і CSRF; глобальні правила залишаються owner-only.
- Vehicle candidates читають тільки актуальну підтверджену власну конфігурацію. Публічний пошук за моделлю не розкриває її чи VIN. Старі fitment assertions не підтверджують нові додаткові характеристики, якщо їх доказ не охоплює.

## Перевірка та Stage 2

Усі DB-тести стирають виключно окрему локальну `warehouse*_test` БД. Офлайн-аудит не потребує DB:

```bash
cd warehouse/backend
python scripts/audit_canonical_coverage.py --output /tmp/canonical-A-terms.json
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_catalogue_v2_suite_test python -m pytest -q
python -m alembic heads
```

До Stage 2 готові універсальні ідентичності, позиції/варіанти, provenance, групове owner-погодження, умови застосовності та підтверджувана конфігурація. **До автоматичного повного розбору не готово:** 84,43% пропозицій ще без перевіреного типу; не перевірено B, немає повного технічного fitment/заводських опцій, потрібен окремий генератор preview та явна транзакція створення нових планів. Існуючі плани ніколи автоматично не перегенеровуються.

Найбільші точні групи містять «монітор дисплей навігація», ключі з кількістю кнопок та неповні описи. Без перевірки функції/комплектності та обладнання їх об’єднання небезпечне. Не збільшували показник нечітким збігом чи автоматичним погодженням OEM.

Фінальні локальні перевірки:

- Повний backend: **420 passed, 1 skipped**, 301,75 с; пропущено opt-in benchmark.
- Після додавання двох крайових сценаріїв і прямої перевірки immutable-trigger: **20 passed**, 7,70 с (`test_canonical_v15.py`); результати перекривають повний набір, не підсумовуються.
- Frontend: **321 unit tests passed**, TypeScript/Vite build успішний.
- Єдина Alembic-head `76af12de4b90`; populated upgrade/downgrade regression пройшов у повному наборі; `alembic check`: No new upgrade operations detected.
- `git diff --check` без помилок; зміни виключно `/warehouse`. Жодного push/deployment/staging apply.
- Перевірені cross-brand identity, бензин/дизель, HEV/PHEV/BEV, точний код, сторони/позиції/порядкові номери, OEM, неповні назви, повторення, price-only update, group conflicts/exceptions/stale token, append-only history, crash/retry, allowlist/CSRF/workspace, незмінність старих таблиць включно зі складом/фінансами/планами.
