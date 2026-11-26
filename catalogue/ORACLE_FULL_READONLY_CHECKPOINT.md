# CarPot Oracle — Full Read-Only Catalogue Access
2026-11-26 · Candidate, not live accepted

Base: b08ad15a1b28879e918fbe072a2c2e8c20b2cdc2 (Catalogue PR #580).
Observed live: Skoda 18248 identity returns data; audit/articles/oem return HTTP 503.
Oracle VM SSH authorization remains unconfirmed. No production, database, Railway or IAM change made by this package.
Four candidate routes: prd-page, products, categories, part-articles. Source names and exact supplier/article identity are retained; no fitment claims.
CI, real SELECT grants, index plans, import completeness and commercial namespace are mandatory before deployment.
Remaining: native category hierarchy, technical article metadata, reverse vehicle compatibility, bounded catalogue statistics, MCP registration, ten-vehicle live audit and Warehouse comparison.
Do not present source assembly group as verified node name; no fake counts or graph publication. 

## 26 листопада 2026 · живий граф і довідник

Реалізацію підготовлено поверх Draft PR №582. Авторизований Catalogue staging читає точну модифікацію через наявний приватний Oracle Adapter. Ідентичність охоплює `kind`, виробника, модель і модифікацію. Граф містить джерельні PRD, вузли PDS і точні пари постачальник–артикул. OEM шукається пакетами за виробником автомобіля й приєднується до підтверджених артикулів. Кеш має короткий строк дії. Коли живий Oracle недоступний, Catalogue може повернути чинну версію підтвердженого легкового графа з тією самою ідентичністю.

Категорії підраховуються за назвами груп PRD. Ідентифікатори PDS зберігаються у джерельних даних. Для підкатегорій повертається `null` до підтвердження ієрархії у БД. Кількість позицій означає типи, запропоновані для фізичної перевірки під час розбору. Обсяг фізичного складу визначається фактичним надходженням.

### Фактична перевірка чинного staging

- Catalogue deployment `ceb3fea8-6005-4455-bb34-04f678ff8f67` працює на `b08ad15a1b28879e918fbe072a2c2e8c20b2cdc2`.
- Oracle Read Only повернув характеристики DAF FT 8387 і Volvo 107555. Поточний граф повідомив `namespace_not_published` для DAF і `source_scope_unverified` для Volvo.
- Вибірки PRD для Volvo 107555, Škoda 18248 та BMW 21 містили зв’язки. Вибірки були обрізаними, тому повні кількості залишаються невідомими.
- У Railway зафіксовано сім відповідей HTTP 503 для `audit`, `articles` і `oem` за 330–567 мс. Поточний журнал Gateway містить тільки `ValueError`. Для цих відповідей SQL-ліміт 3 с не вичерпано. Новий код журналює маршрут, категорію помилки, клас і тривалість. Адаптер додає код MySQL без тексту SQL або секретів.
- Сесія не має доступу до Oracle VM через приватний маршрут. Версію розгорнутого адаптера, права SELECT, живий EXPLAIN, готовність таблиць і комерційне значення `ORACLE_COMMERCIAL_LINKAGE_TYPE` треба підтвердити на вузлі. Повні показники, нативну ієрархію, характеристики артикулів і зворотну сумісність не верифіковано.

### Відновлення роботи

Під’єднайте сесію Codex до приватного staging Oracle Adapter на `carpot-oracle` через затверджений канал. Перша перевірка на вузлі використовує чинного SELECT-only користувача. Перевірити версію приватного процесу, `information_schema.COLUMNS` і `STATISTICS` для таблиць адаптера, доступ SELECT, плани `EXPLAIN` для точних ідентичностей і комерційний дискримінатор. Зафіксувати доведене значення у чинній конфігурації адаптера. Після приймання оновлення зберегти попередній файл адаптера та використовувати Railway deployment `ceb3fea8-6005-4455-bb34-04f678ff8f67` як точку відкату Catalogue. Спочатку перевірити приватний адаптер, потім Catalogue staging і тільки після цього Warehouse staging на окремій тестовій компанії.

### Підтвердження з Oracle VM

Власник перевірив чинний процес через SSH. Файл адаптера датований 22.11.2026 16:45. Журнал процесу зафіксував 404 для відсутніх audit/articles/oem. Gateway повертав 503. Окремий OEM-пошук за артикулом повертає 200.

MySQL 8.4.13 і `@@transaction_read_only=1` підтверджені. Ідентичності трьох контрольних модифікацій підтверджені. Для чинного користувача адаптера чотири SELECT-проби повернули MySQL 1142. Після надання табличного SELECT на `commercial_vehicle_pds`, `prd`, `suppliers` і `article_links` повторно перевірити видимість `commercial_vehicle_pds.PRIMARY`, `article_links.linkageid` і комерційний дискримінатор. Результат попередньої проби: `ready_to_install=false`, значення linkage type ще не підтверджене.

Діагностичний скрипт і версія адаптера зафіксовані в `a55d6d8a081d0d7e4163ea456c8e161d45dc1aa8`. Інсталятор у `b8cf418eb5f58bc3688f6c1a5efd7291a09bf2ef` перевіряє SHA-256, зберігає попередній файл і drop-in, використовує підтверджений linkage type, перезапускає лише `carpot-oracle-adapter.service` і перевіряє локальні маршрути. Ручний відкат: `sudo /var/backups/carpot-oracle-adapter/latest-stage13/rollback.sh`. [Draft PR №584](https://github.com/TsPa33/telegram-bot/pull/584)

Після надання чотирьох табличних SELECT користувачу `carpot_catalogue_ro@127.0.0.1` підтверджено доступ до таблиць. Жива схема використовує `commercial_vehicle_pds.commertialvehicleid` і первинний ключ `(commertialvehicleid, nodeid, productid, supplierid)`. Таблиця характеристик використовує `commercial_vehicle_attributes.commercialvehicleid`. Індекс `article_links.linkageid` підтверджено. Обмежені вибірки Volvo 107555 і BMW 21 повернули по 501 зв’язку за 2 мс і 16 мс. Це ліміт вибірки, тому повні кількості залишаються невідомими.

Адаптер 0.4.1 та оновлений SELECT-only probe зафіксовані у `429133a32bbd9ff27f198b9e9c332eae07cefd18`. Проба шукає узгоджені linkage type серед різних комерційних моделей. При колізії числових ID зараховуються лише PDS-пари, відсутні в легковому namespace. Використовувати інсталятор, що закріплює цей SHA. Встановлення очікує підтверджене числове значення.

Остання жива перевірка підтвердила доступ SELECT та всі необхідні префікси індексів. ID 14497 і 18987 дали прямі збіги типу 16, а в інших контрольних ID спостерігалися також типи 7 і 14. Окрема вибірка ID 8346 завершилася MySQL 3024. За таблицею 400 і ключем 271 TecDoc тип 16 є прямим CV target, 7 — CV Producer-ID, 14 — EngineNo. Виправлення 0.4.2 перевіряє рівність `linkagetypeid=16` і точну CV PDS пару товару та постачальника в різних моделях. Підрахунок збігів інших доменів вилучено з рішення про встановлення. [TecDoc Data Format](https://dwnld.aws.tecalliance.com/TecDoc/Downloads/TecDoc-Data-Format.pdf#page=183)
