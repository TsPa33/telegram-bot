# Aleto Catalogue v1 — аудит, реалізація та перевірка

Робоча гілка: `feature/carpot-warehouse-mvp`, база реалізації `df79988d9503869f037a090e1c9075f17a43dda4`.
Змінено лише `warehouse/`. Основний Telegram-бот не запускався і не змінювався. Push, merge, deployment та підключень до production-БД не виконувалося.

## Аудит архітектури

Warehouse — окремі FastAPI API, React/Vite UI, PostgreSQL та Alembic. Використовує тільки `WAREHOUSE_DATABASE_URL`, а не `DATABASE_URL` основного CarPot. Конфігурація вже забороняє назви БД без префікса `warehouse` / `carpot_warehouse`.

- `vehicles`: tenant-local донори; виробник і модель — текстові поля, а не FK на глобальний автомобільний довідник. Залишено незмінними.
- `categories`: tenant-local дерево `category → subcategory → part`; ідентичність імпорту раніше визначалася `(account_id, source, external_key)`. Новий імпортер додатково зіставляє нормалізовані назви **у межах одного батька та типу**, з явними семантичними відповідностями; зберігає існуючі ID, назви та походження. Неоднозначні/архівовані збіги переривають транзакцію.
- `parts`: реальні залишки, продажні ціни, собівартість, OEM та артикули власника. Імпортер не пише сюди.
- `operations`, замовлення та їх події: історія складу/фінансів. Імпортер не дописує й не змінює її.
- `dismantling_items`: потенційний план розбору, незалежний від складу. Локальний базовий довідник і Plan.Parts продовжують працювати.
- Особисті сесії, workspace isolation, CSRF та allowlist маршрутів залишаються чинними. Новий HTTP-маршрут лише читає довідник; потребує одночасно `vehicles.view` і `catalog.view`. HTTP-імпорт не додано.

Виявлено залежність readiness команди від старої поточної Alembic-ревізії. Виправлено: перевіряється актуальний packaged head, потім фактичні таблиці, обмеження ролей і тригер незмінності аудиту. Мінімальна командна ревізія в контракті не змінена. Шість старих тестів оновлено на нову head-ревізію без послаблення перевірок.

## Нові таблиці та межі даних

Міграція `b8716962f6b8`, батьківська `b94f62d18e07`, створює тільки п'ять нових таблиць та їх індекси/обмеження:

| Таблиця | Призначення |
| --- | --- |
| `aleto_models` | Volvo XC40, XC60, XC90 у кожному імпортованому workspace |
| `aleto_offers` | Ідентичність `(account_id, source='aleto', source_article)`, вихідна назва, OEM, стан, URL, останній час спостереження |
| `aleto_prices` | Окремі незмінювані імпортером спостереження цін UAH/USD: `(offer_id, observed_at)`; NULL залишається NULL |
| `aleto_applications` | Зв'язки пропозиція–модель, складені FK забезпечують відповідність workspace |
| `aleto_taxonomy` | Вихідні назви категорії/підкатегорії, зв'язок з існуючим деревом, `verified` або `pending` |

Новіше спостереження доповнює історію цін і оновлює лише метадані вихідної пропозиції. Старіше не замінює актуальну пропозицію. Суперечливі дані за той самий timestamp відхиляються, усі зміни транзакції відкочуються. Повторне джерело не видаляє відсутні у ньому старі записи. Окремий workspace блокується на час імпорту, включно з dry-run, для серіалізації конкурентних запусків.

У міграції немає завантаження даних із мережі. Downgrade видаляє тільки Aleto-таблиці; додані у спільне дерево категорії залишаються. Перед downgrade архівуйте довідкові дані, якщо вони потрібні; склад та його історія не видаляються.

## Нормалізація та інтеграція

`aleto_subcategories_uk.json` — явний словник усіх 264 вихідних назв. 263 мають українську відповідність; `Комп` неоднозначне і навмисно має `null`. Runtime не перекладає замінами літер, не використовує fuzzy matching і не відкидає непізнані назви: їхні шляхи зберігаються як `pending`. Словник пройшов технічну перевірку покриття; окреме предметне погодження перекладів власником каталогу не виконувалося.

Назви з модельними роками мають окремі явні записи у словнику; вони зведені до назв типів деталей. Вихідні назви повністю залишаються в `aleto_taxonomy`. Це **не** встановлює сумісність для будь-якого конкретного року. База і API не заявляють рік, VIN чи OEM-сумісність: `year_compatibility='unverified'`.

Додавання автомобіля отримує три Volvo-моделі через існуючий `/vehicle-catalog`. У картці автомобіля доступний розділ «Aleto — довідник пропозицій»: фільтри за категорією/підкатегорією, пошук назви/артикулу/OEM, пагінація, URL джерела, час і «Ціна Aleto (орієнтир)». Розділ завантажує дані лише після розкриття.

Підготовка плану розбору додає **один потенційний тип на перевірену підкатегорію**, а не тисячі альтернативних пропозицій як складські деталі. Нові Aleto-пункти мають `included=False`: для фактичного надходження користувач повинен включити їх і виконати стандартне підтвердження складу. При надходженні повторно використовуються категорії, об'єднані під час імпорту. Ціни/OEM/артикули пропозицій не копіюються автоматично до власних складських позицій. Імпорт не змінює плани існуючих донорів; вони доповнюються лише звичайною явною підготовкою плану.

## Перевірений імпорт повного пакета

Джерело: `prepared/aleto_staging.sqlite3` із прикріпленого архіву. SHA-256:
`c2cdde72685a6f41c70922e569fd8eae81e8bcbd292273fa411314dd920dccd3`.

SQLite відкривається read-only; перевіряються integrity/FK, артикули, зв'язки, набір моделей, таксономія, точність і невід'ємність цін, HTTPS Aleto URL та timezone timestamp. Скрипт `prepare_import.py` з архіву не виконувався; його README використано як відомості про дані, а не як додаткову авторизацію дій.

Тестове середовище: PostgreSQL 16.15, окрема локальна БД `warehouse_aleto_test`; тестовий workspace з наявними донором, запчастиною з власними цінами, аудитом та категорією «Салон».

| Сутність | Перший apply: додано | Повторний apply: додано / оновлено |
| --- | ---: | ---: |
| Моделі | 3 | 0 / 0 |
| Категорії + підкатегорії | 110 | 0 / 0 |
| Пропозиції | 7 246 | 0 / 0 |
| Спостереження цін | 7 246 | 0 / 0 |
| Зв'язки модель–пропозиція | 10 112 | 0 / 0 |
| Вихідні шляхи таксономії | 14 400 | 0 / 0 |

Одну існуючу категорію «Салон» повторно використано; після злиття всього 10 категорій і 101 підкатегорія. Збережено 421 відсутню UAH-ціну, 131 відсутній OEM. 139 шляхів із назвою `Комп` залишено pending; їхні пропозиції доступні у довіднику, але вони не створюють автоматичних типів плану.

Зв'язки й HTTP-вибірки: XC40 — **1 472**, XC60 — **4 155**, XC90 — **4 485**. Це модельні групи джерела, не підтверджена сумісність конкретних машин.

До та після dry-run/apply/reapply порівняно рядки всіх 20 початкових таблиць: жодного зміненого/видаленого рядка; лише додано категорії. Dry-run не залишив нових Aleto-рядків. Після цього функціональні UI/API-перевірки створювали тільки тестових донорів і плани в цій тестовій БД.

Машинні звіти: [dry-run.json](dry-run.json), [apply.json](apply.json), [reapply.json](reapply.json).

## Відтворення без production

Потрібні Python 3.11+, PostgreSQL, Node/npm. Команди виконуються в указаних каталогах; БД має бути **окремою тестовою**, з назвою `warehouse*_test`. Для ізольованого staging додано окремий явний `--staging` із перевіркою середовища та назви БД; production заборонений. Точні команди — у [STAGING.md](STAGING.md).

```bash
# /workspace/telegram-bot
uv venv --python 3.11 /workspace/.venvs/warehouse
uv pip install --python /workspace/.venvs/warehouse/bin/python \
  --require-hashes -r warehouse/backend/requirements.lock
export PATH=/workspace/.venvs/warehouse/bin:$PATH

cd warehouse/backend
# Використайте захищено налаштований URL окремої тестової БД:
export WAREHOUSE_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_aleto_test'
python -m alembic upgrade head
python -m alembic check
```

Створіть тестового директора через локальну форму реєстрації (bootstrap `app.create_owner` призначений лише для staging); візьміть його workspace ID з `/api/v1/auth/me`. Для браузера на HTTP потрібне `WAREHOUSE_COOKIE_SECURE=false` лише у локальному тестовому процесі. Архів розпакуйте у окремий каталог; не запускайте вкладених скриптів.

```bash
# warehouse/backend; ALETO_STAGING_DB — шлях до підготовленого SQLite,
# ALETO_TEST_ACCOUNT_ID — ID тестового директора, не працівника.
python -m app.services.aleto_import "$ALETO_STAGING_DB" \
  --account-id "$ALETO_TEST_ACCOUNT_ID" --dry-run --report /tmp/aleto-dry-run.json
# Відсутність прапорців режиму також означає dry-run.
python -m app.services.aleto_import "$ALETO_STAGING_DB" \
  --account-id "$ALETO_TEST_ACCOUNT_ID" --apply --report /tmp/aleto-apply.json
python -m app.services.aleto_import "$ALETO_STAGING_DB" \
  --account-id "$ALETO_TEST_ACCOUNT_ID" --apply --report /tmp/aleto-reapply.json
```

Секретів або URL з production не потрібно. Імпортер не надсилає повідомлень, не звертається до Aleto та не запускає бота. Неповний пакет, суперечності, проблеми категорій чи FK дають невдалий exit status; apply є однією атомарною транзакцією, dry-run виконує той самий план з rollback.

Тести **очищують** свою БД: використовуйте іншу БД, наприклад `warehouse_aleto_suite_test`, щоб зберегти повний імпорт для ручного перегляду.

```bash
# warehouse/backend
export WAREHOUSE_TEST_DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_aleto_suite_test'
python -m pytest tests/test_aleto_catalogue.py -q
python -m pytest tests unit_tests -q

# warehouse/frontend
npm ci
npm run build
# Перший термінал, warehouse/backend, URL імпортованої тестової БД:
WAREHOUSE_COOKIE_SECURE=false python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
# Другий термінал, warehouse/frontend:
npm run preview -- --host 127.0.0.1 --port 18765 --strictPort
# Третій термінал; тестовий workspace з імпортом і донором Volvo XC40:
# ALETO_TEST_EMAIL / ALETO_TEST_PASSWORD задайте для тестового акаунта.
WAREHOUSE_E2E=1 node tests/aleto-catalogue.mjs
```

Для браузерної перевірки використовуються **зібрані production-assets через локальний preview**, без deployment. У вихідному dev-режимі помічено окрему наявну проблему StrictMode/ініціалізації сесії в `App.tsx` (екран підготовки зависає); цей файл не змінено, вона поза інтеграцією Aleto. У зібраному UI цього блокування немає.

## Обмеження

Каталог є частковим crawler export. Немає підтвердження повноти чи сумісності за роком/VIN/комплектацією. `Комп` потребує предметного розшифрування; невідомі назви не перекладаються автоматично. Публічного/production використання джерела та deployment не виконано. Для production потрібні окремий дозвіл, погодження даних/прав використання та окремий операційний процес; CLI підтримує лише тестову БД або явний ізольований staging; production не підтримує.

## Підсумок виконаних перевірок

- `pytest tests unit_tests -q`: **328 passed, 1 skipped**, 177.80 с. Пропущено тільки опційний `WAREHOUSE_SMART_PERF` benchmark на 100 000 рядків. Один наявний deprecation warning Starlette/httpx.
- Нові `test_aleto_catalogue.py`: **28 passed**; dry-run rollback, apply/reapply, одночасні імпорти, злиття категорій, NULL, історія цін, stale replay, конфлікти та rollback, валідація зв'язків/цін, pending-назви, доступ/tenant isolation, інтеграція плану та явного надходження, заборона нетестової БД, upgrade/downgrade і незмінність складу/аудиту. Для перевірки незмінності є непорожній залишок, ручний резерв та замовлення з USD-ціною.
- `alembic check`: **No new upgrade operations detected**. Міграційні round-trip тести успішні.
- `npm run build`: TypeScript та Vite **успішні**.
- `tests/aleto-catalogue.mjs`: **два успішні viewport — 1440 px і 390 px**, реальна локальна API та повний імпорт; пошук, фільтри, посилання джерела, попередження про непідтверджену сумісність; без JS-помилок.
- Існуючий `tests/plan-parts-checklist.mjs`: **desktop + iPhone passed**.
- `/health` і `/api/v1/team/readiness`: **200** з новою ревізією. HTTP-вибірки XC40/XC60/XC90 відповідають 1 472/4 155/4 485.
- `git diff --check`: **успішний**; усі змінені/нові файли виключно під `warehouse/`.

## Перелік змінених файлів

У локальному коміті 33 файли, усі під `warehouse/`:

- `backend/alembic/versions/b8716962f6b8_aleto_reference_catalogue_v1.py`
- `backend/app/api/aleto.py`
- `backend/app/api/team.py`
- `backend/app/data/aleto/v1/catalogue.sqlite3.gz`
- `backend/app/data/aleto/v1/manifest.json`
- `backend/app/data/aleto_subcategories_uk.json`
- `backend/app/main.py`
- `backend/app/models/__init__.py`
- `backend/app/models/aleto.py`
- `backend/app/permissions.py`
- `backend/app/route_registry.py`
- `backend/app/services/aleto_catalog.py`
- `backend/app/services/aleto_import.py`
- `backend/app/services/dismantling.py`
- `backend/app/services/vehicle_catalog.py`
- `backend/tests/test_aleto_catalogue.py`
- `backend/tests/test_dismantling_readiness.py`
- `backend/tests/test_dismantling_v2.py`
- `backend/tests/test_plan_parts_migration.py`
- `backend/tests/test_quick_vehicle.py`
- `backend/tests/test_smart_migration_permissions.py`
- `backend/tests/test_staging.py`
- `docs/aleto/README.md`
- `docs/aleto/STAGING.md`
- `docs/aleto/apply.json`
- `docs/aleto/bundled-dry-run.json`
- `docs/aleto/dry-run.json`
- `docs/aleto/reapply.json`
- `docs/aleto/validation.json`
- `frontend/src/AletoCatalogue.tsx`
- `frontend/src/VehicleForm.tsx`
- `frontend/src/pages/Vehicles.tsx`
- `frontend/tests/aleto-catalogue.mjs`

## Доповнення: GitHub Push & Staging Preparation

Повний пакет тепер збережено у `backend/app/data/aleto/v1/catalogue.sqlite3.gz` з `manifest.json`, а не тільки у локальній тестовій БД. Додано явний staging-режим CLI та 11 перевірок portability/цільового середовища. [STAGING.md](STAGING.md) містить команди preflight, міграції, dry-run, apply та recheck, а також статус перевірки Auto Deploy. Новий [bundled-dry-run.json](bundled-dry-run.json) підтверджує завантаження переносного пакета й нуль змін у вже імпортованій тестовій БД.

Фінальний повторний backend-прогін після додавання переносного пакета і staging-режиму: **328 passed, 1 skipped**, 177.80 с.; нові Aleto-тести — **28 passed**. `alembic check`, перевірки staging-конфігурації/Watch Paths і staged SHA-256 успішні. Railway isolation не підтверджено; за прямою умовою користувача виконується лише локальний commit, без push.
