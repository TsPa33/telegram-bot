# Етап 1.4 — фактичний стан Volvo №30: BLOCKED

Дата перевірки доступу: **2026-11-11** (Europe/Kyiv).

**Фактичні staging-дані не отримано. READY FOR PREVIEW не підтверджено.** Жоден локальний fixture, попередній скриншот або packaged schema не використано як доказ стану автомобіля №30. Звітом не підтверджується ані наявність, ані відсутність його деталей.

## Підтверджені перевірки

- Репозиторій `TsPa33/telegram-bot`, гілка `feature/carpot-universal-dismantling-catalogue`, clean worktree перед створенням звіту.
- Local HEAD і remote Git transport (`git ls-remote origin refs/heads/feature/carpot-universal-dismantling-catalogue`) збіглися: **`429402509c7a6cdc7fefc35a7cb185f6be638c2e`**. Це GitHub SHA, не deployed SHA.
- У поточному наборі connector tools **немає Railway або авторизованого browser connector**. Companion Page не містить документа чи авторизованої сторінки.
- `command -v railway` не знайшов CLI. Railway config відсутній як у home, так і в репозиторії.
- Перевірено лише наявність, без друку значень: `RAILWAY_TOKEN`, `RAILWAY_API_TOKEN`, `RAILWAY_PROJECT_TOKEN`, `WAREHOUSE_DATABASE_URL`, `WAREHOUSE_STAGING_DATABASE_URL`, `WAREHOUSE_STAGING_READONLY_DATABASE_URL`, `DATABASE_URL`, `WAREHOUSE_STAGING_URL`, `WAREHOUSE_STAGING_API_URL` — **NOT_SET**.
- У репозиторії знайдені лише `.env.example` та `deploy/railway/staging.env.example`, а не runtime credentials.
- Єдина HTTP-спроба: неавторизований GET `https://backboard.railway.com/graphql/v2`, timeout 12 секунд. Результат: **`URLError: <urlopen error Tunnel connection failed: 403 Forbidden>`**. CONNECT tunnel відхилений до отримання відповіді Railway. Це блокування мережевого доступу, не доказ стану Railway-проєкту. Відповідь/секрети не друкувалися. **Повторних спроб не виконано.**
- До PostgreSQL, Warehouse API та джерел цін підключень не відкривали; production не використовували.

## Інфраструктура: очікуване та фактичне

| Об’єкт | Очікуване за контекстом завдання | Фактична перевірка |
|---|---|---|
| Project | selfless-caring; раніше вказаний ID ff2f3a14-2ffa-49ba-9b9d-9889ce98da5d | UNVERIFIED |
| Environment | warehouse-staging; раніше вказаний ID e9d04365-fc5a-4ba2-84a7-275c44580fe8 | UNVERIFIED |
| Web | confident-sparkle | Service bindings/status/deployed SHA UNVERIFIED |
| API | telegram-bot | Service bindings/startup/deployed SHA UNVERIFIED |
| Worker | warehouse-import-worker | Існування/status/deployed SHA UNVERIFIED |
| PostgreSQL | окремий staging postgres | Ізоляція, host, database, роль read-only, schema/revision UNVERIFIED |
| CarPot URL | не підтверджений у поточному доступі | Не вигадано; browser QA UNVERIFIED |

`warehouse/deploy/railway/import-worker-service.json` — **preparation checklist**, а не фактичний Railway binding. Файл містить стару запропоновану branch `feature/carpot-warehouse-mvp`; це не доказ, що active worker використовує саме її. Налаштування не змінювалися. Відповідність активних deployments поточній GitHub-гілці не встановлено.

## Ідентифікація автомобіля

За чинною моделлю `Vehicle` (`backend/app/models/__init__.py`) `number` та `id` — різні поля; номер унікальний **лише в account/workspace** (`uq_vehicle_account_number`). Отже, `№30` не є запитом `id=30`, а номер без workspace недостатній для ідентифікації.

| Поле фактичного запису | Результат |
|---|---|
| Vehicle database ID | UNVERIFIED |
| Workspace/account | UNVERIFIED; приватні дані не отримані |
| Марка/модель/покоління | Очікується Volvo XC90 II; фактичне значення UNVERIFIED |
| Рік | Очікується 2016; фактичне значення UNVERIFIED |
| Модифікація, K-Type, global car_id | UNVERIFIED; не підставляти контрольний car_id=107555 автоматично |
| Двигун, engine code/variant, об’єм, паливо, КПП, привід | UNVERIFIED; не переносити T6/АКПП/AWD із контрольного прикладу |
| VIN | Наявність UNVERIFIED; повний VIN не отримували й не публікували |
| VehicleConfiguration, provenance/confidence/конфлікти | UNVERIFIED |

## UI проти фактичних даних

| Показник | Попереднє UI-значення за користувачем | Фактичний API/DB результат |
|---|---:|---|
| У плані | 113 | UNVERIFIED |
| Підтверджено | 2 | UNVERIFIED |
| На складі | 0 | UNVERIFIED |
| Потребує уваги | 113 | UNVERIFIED |
| Усього DismantlingItem / включено / не включено | Не надано | UNVERIFIED |
| Неперевірені / present / damaged / absent | Не надано | UNVERIFIED |
| Категорії / підкатегорії / без категоризації | Не надано | UNVERIFIED |
| Canonical type / placement links | Не надано | UNVERIFIED |
| Part links / непов’язані Part | Не надано | UNVERIFIED |
| Active та історичні AssemblyMembership | Не надано | UNVERIFIED |
| Повторення source+catalog_key / placement_id | Не надано | UNVERIFIED |
| Ручні inspection-рішення, примітки, кількості | Не надано | UNVERIFIED |
| Залишки / резерви / архівні / продані | Не надано | UNVERIFIED |
| Операції руху й історія вузлів | Не надано | UNVERIFIED |

**Стан двох раніше підтверджених позицій: UNVERIFIED.** Не встановлено їхні ID, назви, presence/inspection, Part, кількості, резерви, історію чи membership. Не стверджуємо, що вони збережені або втрачені в поточному staging; у межах цього завдання їх не читали й не змінювали.

### Що можна встановити з коду, але не з БД

`frontend/src/assemblyOverview.ts` рахує показники через API-проєкцію:

- У плані — кількість `items` із assemblies API; це не обов’язково SQL-count лише `included=true`.
- Підтверджено — `presence in (present, damaged)`. У `services/assemblies.py` presence є похідним також від Part/status/стану компонента; його не можна замінити лише підрахунком `plan_v3.inspection`.
- На складі — `part_id`, немає parent/consumed operation/archive, quantity > 0; це не кількість усіх Part links і не available quantity після резервів.
- Потребує уваги — об’єднання unchecked/damaged/absent, incomplete та невизначеної категорії; не сума взаємовиключних статусів. Відсутня підкатегорія сама по собі не входить у чинну формулу.

Тому `113/2/0/113` логічно можливі, але це **не підтверджує** такі числа для реального №30. Constraints моделі (унікальність source+catalog_key, placement, Part link) також не доводять, що staging має актуальну міграцію або не містить історичних невідповідностей.

## Зіставлення з 113 типами

Підготовлений локальний пакет містить 113 source ID, 101 proposed, 12 needs_review. Це перевірений артефакт каталогу, **не результат зіставлення з фактичним планом**.

| Група зіставлення фактичного плану | Кількість |
|---|---|
| Точний source ID з перевіреним source/car context | UNVERIFIED |
| Явний canonical type/placement ID | UNVERIFIED |
| Неоднозначні / відсутні зв’язки | UNVERIFIED |
| Історичні складські позиції, захищені від змін | UNVERIFIED |
| Позиції без категорій | UNVERIFIED |

Жодну з цих кількостей не підмінено нулем або локальними 113. Однакові назви не використовувалися як доказ тотожності. 101 proposed запис не застосовано.

## Підтверджені невідповідності та ризики

**Даних про фактичні розбіжності UI/DB немає** через блокування доступу. Є такі обмеження перевірки:

1. Неможливо підтвердити isolation staging/production, active SHA, revision і джерело Web/API/worker.
2. Номер без workspace не визначає Vehicle; вибір не того донора створить ризик хибного зіставлення.
3. Рахування SQL inspection замість assemblies presence дасть потенційно інші метрики UI.
4. Повторне застосування лише за назвами може переприв’язати історичні Part або втратити ручні рішення; майбутній preview має використовувати exact source/canonical identity і protection guards.
5. 12 unresolved типів та відсутність доказів VIN/фізичних установчих місць залишаються блокерами повного catalogue review незалежно від доступу до staging.

## План read-only перевірки після відновлення доступу

Це план, **не виконані операції**. Автоматичних виправлень немає.

1. Надати доступний Railway connector/Console read-only export або перевірений staging-only read-only PostgreSQL канал. Credentials передавати поза Git/публічним звітом. Підтвердити project/environment IDs, API/Web/worker bindings, active deployment SHA і staging isolation до підключення.
2. Підключатися без startup Warehouse, тестових fixtures чи міграцій. Для PostgreSQL використовувати окрему роль SELECT та транзакцію `REPEATABLE READ READ ONLY`, bounded statement timeout, завершити ROLLBACK. Спочатку перевірити runtime schema/revision та відповідність коду розгорнутому SHA.
3. Знайти candidates `number=30`, manufacturer Volvo, model XC90, year 2016 у підтвердженому workspace. Якщо записів кілька або дані суперечливі — STOP для уточнення. Фіксувати справжній Vehicle ID; VIN лише ознака наявності/масковане значення.
4. У тій самій snapshot-транзакції SELECT лише необхідні поля Vehicle/VehicleConfiguration, DismantlingItem, Part, AssemblyMembership (active та історичні), Operation; account+vehicle scope в кожному читанні. Не виводити персональні дані або текст приватних приміток; для ручних рішень достатньо ID, статусу та ознаки note/provenance.
5. Порахувати raw/included/presence/category/canonical/Part/membership окремо. Перевірити повторення `(source,catalog_key)` та непорожнього placement ID, account/vehicle consistency, quantities/reserves, archived/sold, movement history. Зіставити assemblies API-проєкцію з формулою UI, не лише зі SQL inspection.
6. Для двох підтверджених позицій зафіксувати ID/inspection/presence, кількості/резерви та зв’язки з історією. Якщо їх більше/менше двох — описати факт без виправлення.
7. Зіставити 113 типів за точним `source ID + контекст car/source`, потім explicit canonical IDs. Розділити ambiguous/missing/protected/uncategorized. Не виконувати provisioning categories, publish, preview endpoint із невстановленими side effects або apply. Скласти пропозицію виправлень лише після фактів.

## Підсумок

**BLOCKED — staging недоступний через CONNECT 403 та відсутні авторизований Railway/DB/browser доступи.** Повний перелік неперевірених умов наведено вище. Нових backend/frontend тестів не запускали: код не змінено, локальні тести не доводять live-стан.

Створено тільки цей звіт. Немає INSERT/UPDATE/DELETE, міграцій, catalogue publish, paid API, deployment, merge PR або втручання в production. Дозволений Git push містить лише документацію. Наступний етап не розпочато.
