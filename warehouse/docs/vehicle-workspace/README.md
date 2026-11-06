# CarPot: єдиний workspace розбору й номерів

Локальна реалізація поверх `32954a6651939fc14fdaeeb1fe42f5c76c1bae6e`.
Затверджений зелений референс використаний для категорій, компактного списку,
бічних дій і вбудованого менеджера. Числа та номери у screenshots — **синтетичні**.

## Що реалізовано

- Одне джерело навігації, одна таблиця, одна вбудована панель артикулів/OEM.
  Корпоративні категорії беруть точну серверну класифікацію. Неоднозначні типи
  залишаються у «Потребують уточнення». Категорії не викликають постачальника.
- Пошук, складські/OEM/snapshot-фільтри, вибір повної відфільтрованої категорії,
  збереження вибору між категоріями, порційне відображення довгого списку.
- Раніше отримані варіанти відновлюються із PostgreSQL. Пакетні запити обмежені
  20 типами за явне підтвердження; показується максимальна сумарна вартість.
  Зупинка припиняє наступні запити, а не видає поточний за скасований.
- Вибраний серверний `art_id` призначається конкретній складській картці після
  повторної перевірки workspace/донора/K-Type/type marker/наявності та блокувань.
  При кількох картках одного типу потрібний явний вибір картки.
  Очікувані старі номер/бренд запобігають тихому перезапису конкурентних рішень.
- Виробник показується поряд з артикулом у «Пошуку запчастин». Пошук по номеру/OEM
  використовує наявний API. Пошук у загальному складі **за самим брендом** тут
  не додавався; локальний фільтр workspace бренд враховує у призначених
  номерах і відкритих source variants. Глобальний пошук усіх ще не відкритих
  variants у snapshots — окреме наступне розширення.
- Ручна зміна номера у картці очищує попередній supplier brand/provenance,
  щоб старе походження не підтверджувало новий номер. Омітовані номер/OEM
  у старій формі більше не стирають уже призначені значення.
- OEM залишається окремим полем з ручним підтвердженням і provenance. API OEM
  вимкнений: endpoint, контракт і тариф не підтверджені. Aftermarket не стає OEM.
- Використовується наявний idempotent stock add-batch. По 1 фізичній деталі
  додається тільки після окремого складського підтвердження. Отримання API,
  категоризація та перегляд ніколи не створюють надходжень.

## PostgreSQL та відновлення

Єдина нова head: **`bd18a9f37c20`**, parent **`ac97f052e1b4`**.
Міграція additive: нова `plan_parts_responses`; nullable provenance у `parts`;
nullable response link/metadata у `plan_parts_article_receipts`. Немає backfill,
зміни кількості, reserved, selling_price, receipt, sale або фінансових таблиць.
Downgrade, який видалив би оплачені відповіді, навмисно заборонений.

`plan_parts_responses` зберігає account/actor, початкового донора, resource,
параметри (включно з K-Type/pt_id), request UUID, context hash, status, bounded
sanitized body, SHA-256, normalized records, schema version, timestamps,
estimated maximum і nullable actual token charge. Фактичне списання не вигадується.
Context дедуплікації: workspace + resource + точні параметри; однаковий каталог
можна повторно використати і для іншого власного донора з тим самим K-Type.
Прив'язка до конкретної фізичної картки зберігається окремо в provenance.

1. PostgreSQL advisory transaction lock + unique pending/uncertain context.
2. Намір `pending` **commit до HTTP**.
3. Повне HTTP 200 тіло — **commit до JSON/domain parsing**.
4. Окремо validated normalized projection та completeness `complete/partial/unknown`.
5. Immutable body/hash trigger. Перевірка SHA перед replay/download.

Невалідна HTTP 200 не зникає після restart. Парсер можна виправити й перечитати
збережені bytes без нового HTTP. Порожній `[]` є повноцінним результатом.
Unknown public fields зберігаються у body, навіть якщо typed projection їх ще
не використовує. Provider count > returned count позначається partial; це не
повний каталог і не привід автоматично оплачувати наступні сторінки.

При timeout/crash або помилці запису тіла durable intent залишається
pending/uncertain і блокує нову оплату, включно з новим UUID/force.
Немає обіцянки відновити bytes, які не встигли потрапити в PostgreSQL: такий
випадок потребує звірки з постачальником. Автоматичного paid retry немає.
Історичні receipts без snapshot/raw не можуть бути відновлені «з нічого».

Зберігаються максимум 2 MiB і 10 000 записів відповіді. HTTPS fixed source,
redirects OFF, timeouts збережені. Ключ не потрапляє у payload/log/UI;
known credential/contact keys і email redacted перед збереженням. SHA описує
**збережені sanitized bytes**, не претендує на checksum оригіналу до redaction.
До дозволу нового збору треба перевірити відсутність інших PII у реальному
контракті та право retention/reuse. Це не підтверджено публічними fixtures.

GET `/plan-parts/workspace?vehicle_id=…` — read-only, без payload download/N+1.
GET `/plan-parts/responses/{id}` — owner-only scoped download, no-store,
attachment, SHA header. Немає довільного account_id із браузера.
POST lookup/recover/assignment зберігають сесії, CSRF та серверну RBAC.
Маршрути articles/history та donor-parts/article/select додані до fail-closed
route registry: їхня відсутність раніше блокувала чинні handler-и.

## Plan.Parts: підтвердження і конфігурація

Див. [матрицю API](API_MATRIX.md). Зовнішній probe публічного кореня `https://plan.parts/`
заблокований мережевим CONNECT 403 у середовищі Codex. Це **не** доказ відмови
самого API. Нової live-відповіді, тарифів або дозволу на збереження не отримано.

Нові платні cold requests fail-closed без server-side підтверджень:

- `WAREHOUSE_PLAN_PARTS_STORAGE_APPROVED=true` — лише після перевірки умов/PII.
- `WAREHOUSE_PLAN_PARTS_TOKEN_MAXIMA` — JSON object з перевіреними максимальними
  токенами за один resource: brands/models/modifications/categories/articles/ktype.
  Значення — integer 0…10000; непідтверджені ресурси треба **не додавати**.
- Чинні `PLAN_PARTS_ENABLED`, `PLAN_PARTS_API_KEY` залишаються server-only.
- Кожна нова операція потребує UUID, `confirm_paid=true` та підтвердженого
  `max_tokens`; нижчий за серверний максимум бюджет забороняється.

Не копіювати синтетичні тарифи з тестів у Railway. Змінних Railway не змінювали.
Saved replay працює без API key, PLAN_PARTS_ENABLED та нових policy variables.
Старі клієнти можуть читати збережене; cold paid calls без нових підтверджень
отримують 428/503. Старі окремі компоненти збережені для сумісності даних, але
професійний workspace більше їх не монтує як дублюючий сценарій.

## Базовий каталог понад 357

357 — розмір одного source response, не системний ліміт. Наявний універсальний
пакет містить 216 конструктивних функцій / 227 установчих позицій; інший
історичний K-Type fixture — 632 source types. Це різні сутності.

Архітектура розширення:

- Canonical конструктивна функція + перевірений provenance, без прив'язки до бренду.
- Установча позиція (сторона/вісь/умовна комплектація) — окремо від функції.
- Source type, статті/артикули й OEM cross — доказ/довідник, не фізична кількість.
- Configuration-aware candidates — «Потрібно перевірити» при невідомій комплектації.
- Review точних відповідностей; неоднозначні legacy залишаються ручними.
- DismantlingItem і фізичний Part/receipt — тільки явна дія користувача.

Для наступного розширення потрібний reviewed пакет технічних назв/правил з
provenance, preview/diff покриття та окрема публікація. У цьому завданні нові
сотні stock rows не генеруються, canonical snapshot не публікується.

## Перевірки та відтворення

Лише Docker PostgreSQL на loopback `127.0.0.1:55440`, окремі `*_test` БД.
Backend тести стирають **тільки цю тестову БД**; production/staging URL не брати.

```sh
# warehouse/backend; LOCAL_TEST_URL — окрема disposable *_test БД
WAREHOUSE_TEST_DATABASE_URL="$LOCAL_TEST_URL" python -m pytest \
 tests/test_vehicle_workspace.py tests/test_plan_parts_article_receipts.py \
 tests/test_plan_parts_batch_stock.py tests/test_plan_parts_direct_stock.py \
 tests/test_plan_parts_category_recovery.py tests/test_plan_parts_stock_classification.py \
 tests/test_plan_parts_cache.py tests/test_plan_parts_cooldown.py \
 tests/test_plan_parts_null_article_names.py tests/test_plan_parts_paid_response_recovery.py \
 tests/test_plan_parts_live_catalog.py tests/test_plan_parts_migration.py \
 tests/test_checklists.py tests/test_orders.py tests/test_sales_center.py -q
WAREHOUSE_CATALOGUE_WORKER_ENABLED=false python -m pytest --noconftest \
 unit_tests/test_plan_parts.py unit_tests/test_plan_parts_real_fixtures.py -q
# warehouse/frontend
npm run build
node --test tests/*-unit.mjs
```

Populated parent upgrade: `tests/verify_vehicle_workspace_migration.py` з двома
явними local URLs (source/target, loopback:55440, різні *_test). Ціль спочатку
порожня; script upgrade ac97, копіює синтетичні старі колонки, upgrade head двічі,
порівнює дані та перевіряє відсутність автоматичних API requests.
Докази — [evidence](evidence/).

Результати фінального прогону: **71 унікальний backend test PASS (70 основних + 1 новий regression;
2 пов’язані перевірки повторено), 38 offline PASS, 537 frontend
unit PASS, frontend build PASS**. Browser 1440/1280/768/390/375 PASS, без
JS errors / горизонтального overflow, категорії не викликають paid lookup.
Synthetic write workflow PASS: присвоєння article/brand, ручний OEM, пошук,
явне одиничне надходження нового типу, повтор без дубліката, quoted MockTransport
request та відновлення після reload. Початкові stock price/quantity незмінні.
Новий backend instance/Session recovery, malformed 200, []/partial, immutable
body, DB write failure, concurrent intents, cross-workspace 404 — автоматичні тести.

Screenshots: [desktop](evidence/workspace-1440.png), [iPhone](evidence/workspace-390.png),
[таблиця desktop](evidence/table-1440.png), [таблиця iPhone](evidence/table-390.png),
[менеджер desktop](evidence/manager-1440.png), [менеджер iPhone](evidence/manager-390.png).
Візуально звірено з зеленим референсом: спільна шапка, категорії, таблиця,
бічні дії та компактна вбудована панель; mobile — картки без широкої таблиці.
Лічильник збережених варіантів рахує отримані асоціації тип–артикул, а не
обіцяє глобальну унікальність артикула між типами.


Browser: `WAREHOUSE_E2E=1`, `WAREHOUSE_DATABASE_URL` — synthetic loopback:55440,
`PYTHONPATH=. python tests/vehicle_workspace_server.py`; потім
`python tests/seed_vehicle_workspace.py` з тими ж variables. API порт 8022,
MockTransport only, workers OFF. Frontend build/preview з
`WAREHOUSE_API_PROXY=http://127.0.0.1:8022`, порт 5223.
`WAREHOUSE_E2E=1 node tests/vehicle-workspace-browser.mjs` і
`WAREHOUSE_E2E=1 node tests/vehicle-workspace-write-browser.mjs`.
Write script очікує свіжий seed, працює лише з явно позначеним synthetic donor.
Не запускати паралельно з pytest: його fixtures очищують цю саму локальну БД.

Початкові 4 audit failures були розбіжностями старих тестів із чинним контрактом:
null part_name дозволений, count може означати total, validated cache hits не
витрачають request gate, success/data/results — допустимий envelope. Тести
виправлені відповідно; додані окремі partial/invalid/recovery assertions.
Старі migration tests перейшли на forward-only перевірки; реальний upgrade
заповненого parent перевірений у другій БД, не замінений no-op upgrade.

## Обмеження перед staging

- Railway bindings/volume/deployed SHA/revision — **UNVERIFIED**, інструментів
  Railway у цій сесії немає. Ізоляцію треба підтвердити перед платними сценаріями.
- OEM API, аналоги, характеристики, OEM/fitment contract і реальні тарифи —
  **UNVERIFIED/DISABLED**. Ручний OEM протестований, API OEM — ні.
- Відомий попередній Alembic metadata drift: назва індексу vehicle directory
  `ix_vehicle_directory_account_id` vs `ix_vehicle_directory_variants_account_id`.
  Ця реалізація не змінює directory/DDL індексу. Тест явно дозволяє тільки ці
  дві старі rename-операції; нових differences немає.
- Повний live-сценарій не оголошується прийнятим. Усі зовнішні API в тестах —
  MockTransport; витрати реальних токенів **0**.
- Push, deployment, staging migration/publish/import та зміни реальних даних
  не виконувалися. Подальший реліз — за окремим дозволом після перевірки gate-ів.
