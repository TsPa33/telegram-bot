# Розширення реальними джерелами — 2026-11-11

## Фактичний результат

Реальні PRD-дані прочитано з наданого `carpot_codex_data.zip`: **26 938 унікальних source ID, 0 повторів source ID**. Контрольні суми вкладених пакетів — [real-prd-summary.json](real-prd-summary.json). Приватну базу та повний PRD у Git не скопійовано.

Наявний попередній screening містить 3 833 запропоновані виключення, 23 105 решту записів і 789 пріоритетних кандидатів на review (це перетин, не додаткові типи). Screening не містить остаточного checksum-bound зіставлення з чинними canonical ID, тому **не перетворений на автоматичне затвердження**. Поточний реальний preview: 26 938 needs_review, 0 затверджених нових типів, 0 опублікованих, 0 об'єднаних синонімів. Підготовлено 54 локальні пакети по ≤500 рядків. Це не фактичне наповнення staging.

Фактична кількість модифікацій з придатними джерельними зв'язками у catalogue-staging **UNVERIFIED**. У цій сесії немає `SOURCE_*` підключення до Windows MySQL або налаштованого авторизованого Catalogue API/Railway. Відомий CONNECT 403 не обходився й не повторювався. Неможливо чесно підтвердити вже завантажені snapshot або додати нові live-зв'язки. Зовнішній блокер наповнення: потрібен перевірений експорт джерельного графа / доступ до чинного catalogue-staging. Українські рішення та неоднозначності залишаються обов'язковим review gate, а не вважаються завершеними.

## Реалізація без нової архітектури

- `catalogue/vehicle_source_batch.py` повторно використовує SOURCE_* connection, collector, contract, compact plan, import_summary, review_taxonomy і snapshot uploader. Нових таблиць немає. Старі назви `catalogue_volvo_*` збережені для сумісності; дані й алгоритм підтримують будь-якого виробника.
- Exact manufacturer/model/car IDs отримуються зі зв'язаних source-рядків, а не зі схожості назви VIN. Model discovery — лише пошук кандидатів; не підтвердження вибору модифікації користувачем.
- Джерело: транзакція `READ ONLY`, SELECT + session timeout; keyset article_links/PRD; максимум 100 модифікацій, 20 000 зв'язків/модифікацію, 8 MiB snapshot. Обидва написання passenger/passanger cars перевіряються по фактичній схемі. Жодних source DDL/індексів.
- Резюмування — атомарні per-modification файли + manifest SHA-256. Змінений запит/checkpoint блокується; раніше збережені exact car IDs залишаються в checkpoint під час discovery-resume. PRD-файл повторно читається тільки після checksum validation; незавершений PRD сканується заново. Консистентність кожного SQL-сеансу не означає незмінність усієї td1q2018 між перезапусками; timestamps/checksums зберігаються окремо.
- PDS-only product IDs і matched product/supplier pairs — окремий звіт. PDS/tree не породжують нові confirmed типи або статичні позиції. Наявність джерельного article_link не доводить заводський BOM.
- OEM фільтрується за фактичним manufacturer_id, а не Volvo=120. Не завантажуються JPG; тільки source metadata, права використання потребують перевірки власником.
- `prepare_universal_catalogue.py` / `universal_catalogue.py` адаптовані з PR #488 без перенесення решти гілки. Нормативні українські назви, corporate category/subcategory, checksum кожного PRD, явні synonym/target-ID рішення. Невідомі/змінені записи блокують publish; нові категорії не створюються.
- Preview/review/publish працюють через **існуючі CanonicalRun + worker/locks + platform-admin/CSRF**, не альтернативну чергу. Повторний publish і повторний пакет не дублюють типи/позиції. Конфлікт source→canonical не переприв'язується автоматично.
- Універсальний генератор читає published reference rows і зіставляє exact modification product IDs з reviewed canonical ID. Кілька явно зіставлених PRD-синонімів дають одну потенційну позицію зі збереженням усіх source refs. Артикули/кількість пропозицій не множать фізичні позиції. Без exact graph залишається існуючий чесно позначений загальний каталог.

## Windows: один експорт

З кореня актуального checkout репозиторію, де вже налаштовано `SOURCE_USER`, `SOURCE_PASSWORD`, за потреби `SOURCE_PORT`; PyMySQL — з чинного `catalogue/requirements.txt`. SOURCE_HOST лише localhost, БД td1q2018. Використовуйте SELECT-only обліковий запис.

```powershell
py -3 .\catalogue\vehicle_source_batch.py export --output C:\CarPot\exports\universal-source-v1 --car-id 107555 --discover-model XC60 --discover-model XC90 --discover-model Golf --discover-model ZOE --max-modifications 8
```

Команда не підключається до Railway, не імпортує й не публікує. Відомий source car_id=107555 — контроль; інші ID не вигадані й будуть записані лише якщо знайдені реальні article_links. Пошук моделей обмежений 100 моделями/запит і 100 модифікаціями/модель; truncation відображається в discovery. Квота по запитах забезпечує різноманітність кандидатів, але не гарантує наявність потрібного року/покоління. Для точного додаткового експорту використовуйте знайдені --car-id, новий output і без discovery.

Потрібні файли: `vehicle_source_batch.py`, `selective_import.py`, `volvo_vehicle_import.py`, `volvo_contract.py`, `volvo_review.py`, `carpot_taxonomy.json`; Python 3.10+ і PyMySQL. Не передавайте пароль у CLI або результатах.

## Контрольований порядок завантаження

1. **Спочатку inventory** через авторизований окремий localhost tunnel у catalogue-staging: `py -3 catalogue\vehicle_source_batch.py inventory --output C:\CarPot\exports\staging-inventory --confirm-catalogue-staging`. Використовує лише SELECT/READ ONLY, чинні DEST_*; порт має відрізнятись від SOURCE_PORT. Відсутність існуючих таблиць — STOP, скрипт не застосовує schema.sql.
2. Порівняти фактично наявні car IDs і SHA з експортом. Для відсутніх/нових — переглянути джерела, права використання й таксономію. Existing same SHA при upload пропускається; different SHA **STOP**, жодного непогодженого overwrite. Зберігаються immutable versions.
3. `validate --output <export> --manifest-sha256 <printed SHA>` — offline перевірка файлів, coverage та source IDs.
4. Український mapping: product ID → `source_sha` (п'ять вихідних PRD-полів), `name_uk`, `category_path` (3 рівні), `kind` (`part/consumable/equipment/review`). `review --output <original> --manifest-sha256 <SHA> --mapping <mapping.json> --reviewed-by <reviewer> --review-output <NEW folder>` створює НОВИЙ reviewed batch/manifest. Оригінал не змінюється. Переклад не підвищує coverage з partial.
5. `upload --output <reviewed> --manifest-sha256 <NEW SHA> --confirm-catalogue-staging` — лише після перевірки tunnel/environment оператором. Не source/prod. Валідація всього пакета перед записами, транзакція на модифікацію, rollback поточної модифікації; раніше успішні модифікації залишаються checkpoint і пропускаються при retry. Model/brand directory пишеться тією самою транзакцією. Concurrent collision — STOP/retry inventory.
6. Каталог уже читається чинними `/api/v1/vehicles/directory`, `/vehicles/{car_id}/plan`, `/articles?product_id=...&snapshot_sha=...`. Немає нового API чи запуску імпорту на API startup.
7. Для загального PRD: `warehouse/backend/scripts/prepare_universal_catalogue.py --input <prd.json> --reviews <reviewed.json> --known-types <existing-types.json> --output <outside-repo report.json> --batch-dir <outside-repo empty dir>`; тільки checksum-bound reviewed records через platform-admin `/api/v1/catalogue/admin/canonical/universal/preview`, далі явний `/publish` з preview_id/token/confirm. Неперевірені пакети не публікувати. Порівняння з актуальними canonical IDs повторюється сервером під час publish, а не довіряє offline файлу.

## Перевірки та контрольні автомобілі

- Backend: 27 PASS (PRD normalization/review, real-sized synthetic stress test, checksum, RBAC/CSRF, CanonicalRun publish/replay, existing IDs, applicability, inventory/membership/history preservation, repeat generation).
- Exact source→canonical synonym regression входить у 27 PASS: canonical reuse тільки при збігу source ID **і PRD checksum**; legacy compact без checksum не переприв’язується автоматично.
- Catalogue: 23 PASS (collector generic OEM, immutable/resumable export, manifests, offline review, PDS gaps, skip/conflict upload, існуючі source/API contracts).
- TypeScript + Vite build PASS. Frontend не змінювався; повторний redesign/browser suite не запускався.
- Volvo XC60 2022, XC90 2016, Volkswagen Golf і Renault ZOE: **синтетичні конфігурації одного генератора**, 216 загальних типів / 227 потенційних позицій. Це не реальні комплектації й не live proof. Фактичні модельні відмінності/source counts — UNVERIFIED до отримання графа; штучні відмінності не створено.
- Реальний PRD scan — окремо від synthetic regression: 26 938 записів, всі невирішені без reviewed mapping; не змішано результати.

Нових міграцій немає. Warehouse/Assembly/резерви/продажі не переписувались. Staging/production MySQL/PostgreSQL writes, платних API, scraping, catalogue publish та ручного deployment у цій сесії не виконано. Після push очікуваний Auto Deploy — **UNVERIFIED**, доки авторизований Railway не підтвердить API/Web SHA. Catalogue runtime API не змінювався; експортер запускається оператором на Windows.

**Статус: OFFLINE IMPORT PIPELINE VERIFIED / LIVE DATA EXPANSION BLOCKED.** Не стверджуємо фактичне розширення понад 216 або завершений review 26 938 записів.
