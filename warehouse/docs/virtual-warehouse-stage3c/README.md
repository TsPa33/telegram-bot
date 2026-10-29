# Stage 3C — ринкові орієнтири та власні ціни

Локальна реалізація поверх Stage 3B `13fe560c4cc9fa4435a83d8c064c4bca6dedaabd`. Push, deployment та запис у staging/production не виконуються. SHA фінального commit див. `git log -1 --format=%H -- warehouse/docs/virtual-warehouse-stage3c` (самопосилання SHA не вбудовується в commit).

## Джерела та достовірність

`services/price_guidance.py` — read-only проєкція існуючих Catalogue v2/v3 і tenant-scoped Aleto v1. Вона не створює Part, receipt, observations, canonical mappings чи продажні ціни. Поточний published snapshot та відбиток правил обов'язкові; SHA mapping перевіряється проти актуальних джерельних полів. Без них немає удаваного точного орієнтира.

OEM нормалізується NFKC/регістром/пробілами; пунктуація й суфікси зберігаються. Перевірена конструктивна функція, модель, установча позиція, відомі обмеження комплектації, OEM і стан перевіряються окремо. Назва чи однаковий OEM самі по собі не доводять взаємозамінність. Fuzzy matching не використовується.

- A: щонайменше 3 різні точні порівнювані оголошення; min/max/median.
- B: 1–2; фактичні ціни з написом «Мало даних», без медіани для автоматизації.
- C: окремі конструктивні приклади з відмінностями, без доказу взаємозамінності; не використовуються у формулах bulk.
- D: «Ціну не визначено»; нуль не підставляється.

Політика `market-guidance.3c.1`: остання observation на offer, не пізніша за поточний час, максимум 90 днів. Не завантажуються всі історичні observations. Дата — спостереження ціни, не публікації оголошення. Невідомий/складний стан не прирівнюється до used. Ціни різних валют та станів не змішуються; FX немає. Зміна дати ціни без прив'язаного до неї стану знижує доказ до C. Дедуп `source/article/currency` усуває повтори шляхів/моделей та v1/v2; суперечливий повтор не входить у точну когорту.

## Фактичний аудит Volvo A

[Машиночитаний звіт](real-a-audit.json) отримано в read-only PostgreSQL-транзакції з локальної копії `warehouse_catalogue_v2_test`. SHA вихідного стисненого пакета A перевірено: `1b6eab050b283cdfa2f068a2e1f187fb525817e8cffed84a91a2b428b16e565a`. Відділено 2 пізні синтетичні пропозиції та один додатковий fixture-шлях.

- Реальний A: 7 246 пропозицій, 14 400 вихідних шляхів.
- Canonical tables/snapshot у цій копії відсутні: фактичне покриття активних Part за рівнями A/B/C/D **не визначено**.
- Лише офлайн-діагностика неопублікованих правил: 1 128 розпізнаних пропозицій, 6 118 нерозпізнаних; 163 потенційні позиції, 160 із хоча б однією валідною ціною.
- Непересічні потенційні групи джерел: 7 позицій мають source-групу 3+, 150 — лише 1–2, 3 — лише функціональні приклади, 3 — без ціни. Це **не** A/B/C/D для конкретного Part: потрібні його OEM, стан, комплектація та опублікований snapshot.
- 2 318 пропозицій мають невідомий стан; серед оброблених шляхів виключення включають невідомий OEM/стан та відсутні ціни — точні лічильники у JSON.

Реальний Volvo B недоступний. Наявні локальні 10 222-рядкові набори мають SYNTHETIC-джерела; вони не видані за Volvo B. Парсер, re-import та реальна canonical publication не запускалися.

Повторити read-only аудит: із backend задати `WAREHOUSE_AUDIT_DATABASE_URL` на loopback `warehouse*_test` і виконати `python scripts/audit_pricing_sources.py --output /tmp/pricing-audit.json`. Скрипт відхиляє зовнішні БД.

## API та власні ціни

- `GET /parts/{id}/price-guidance`, `POST /pricing/guidance` (`ids`, до 1000) — single/batch.
- `GET /parts/{id}/price-context` — власна ціна та CAS token без фінансових прихованих полів.
- Існуючий `PATCH /parts/{id}/price` — ручне встановлення/очищення; сумісний зі старим payload. Новий UI надсилає `expected_token` і `request_key`.
- `GET /pricing/selection` — owner-only вибір за авто, пошуком, категорією/підкатегорією.
- `POST /pricing/previews`, `GET /pricing/previews/{id}`, `POST /pricing/previews/{id}/apply` — durable bulk.
- `GET /vehicles/{id}/parts-valuation` — окрема фінансова інформаційна оцінка.

Усі шляхи під `/api/v1`. Збережено session/CSRF/RBAC, account scope, platform-owner allowlist глобального імпорту. Ручна зміна потребує `parts.change_price`; bulk — workspace-owner DIRECTOR та цей дозвіл. Це не глобальна адміністративна операція. Після очікування блокувань запис повторно перевіряє чинність сесії/акаунта/дозволу.

Ручний workflow змінює лише selling_price/currency та додає звичайний `part_update`. Durable `StockRequest` з окремим domain fingerprint захищає повтори. CAS охоплює зміни Part та останній audit/count (включно з ABA). UI зберігає точний запит до відправлення, не повторює запис автоматично після reload, зберігає введене при помилці та дозволяє явно перечитати поточний стан.

## Bulk та оцінка

Медіана / мінус % / плюс % / фіксована власна ціна; округлення half-up до 1/10/50/100. Формули використовують тільки єдину A-когорту у валюті Part. Фіксований режим не звертається до ринку. Overwrite вимкнений за замовчуванням. Архівні, виключені, нульові залишки та валютні конфлікти пропускаються з причиною.

Preview зберігає команду, докази, власні ціни/revisions, token і строк 15 хвилин. Apply потребує окремого підтвердження; workspace/Part locks у сталому порядку та catalogue advisory lock захищають перерахунок. Зміна даних → 409, потрібен новий preview. Одна транзакція до 1000 деталей; прихованого часткового застосування немає. Durable apply key/fingerprint забезпечує replay після втрати HTTP-відповіді без другого audit. Прострочений, чужий чи інший повторний запит відхиляється. Startup не виконує pricing/apply.

Оцінка авто бере активні непродані quantity, не кількість оголошень. Власні та достатні ринкові ціни підсумовуються окремо за валютою Part. Резерв — частина непроданого залишку, показується окремо, не додається вдруге. Відсутнє покриття не перетворюється на нуль. Це не виручка/прибуток/собівартість. Historical OrderLine/sale snapshots, quantity/reserved, receipts та фінанси не редагуються ціноутворенням.

## Міграція та продуктивність

Єдина нова head `a6d94c72e310` після `95c3e7b12a04`: лише durable `price_decisions` з FK на account/actor та OEM expression indexes існуючих джерел. Немає backfill/import/оновлення Part. Downgrade відмовляється видаляти непорожні durable decisions. Міграція запускається звичайним `python -m alembic upgrade head`; лише локальна БД перевірена, staging не змінювався.

Проєкція batch завантажує контекст деталей разом, обмежує джерела типами/моделями/OEM, бере latest observations SQL DISTINCT ON блоками 500. Request-local memo не переживає запит і не переносить чужий workspace. UI debounce 100 мс, чанки 200 видимих карток, скасування застарілих відповідей. Немає автоматичного запиту всіх автомобілів.

[Замір](performance.json): синтетичні 10 003 оголошення / 300 деталей з однаковими перевіреними критеріями на різних донорах; один і batch мають по 34 SQL. Це перевірка щільної повторюваної вибірки та request-local memo, а не гарантія цього часу для 300 різних конфігурацій. Ліміт матеріалізації — 20 000 mapping-рядків кожного джерела; при перевищенні вибірка явно позначається обмеженою і не утворює A-медіану. До 10 прикладів кожної когорти; повний evidence hash враховує всі її записи. Це обмеження потрібно врахувати при реальному прийманні Volvo B.

## Перевірки та staging

Перед наступним staging deployment потрібен окремий дозвіл на push, перевірка міграції/конфігурації, потім read-only приймання реального Volvo B. Власні ціни змінювати лише явною дією власника, записуване приймання — лише на окремому тестовому донорі.

Запуск перевірок із backend (вони очищують **лише окрему тестову БД**):

```sh
WAREHOUSE_TEST_DATABASE_URL=postgresql+psycopg://postgres@127.0.0.1:5432/warehouse_stage3c_test python -m pytest -q
```

Frontend: `npm run build`, `node --test tests/*unit.mjs`. Browser: створити окрему loopback БД `warehouse_stage3c_browser_test`, застосувати head, запустити `scripts/seed_stage3c_browser.py` із `WAREHOUSE_TEST_DATABASE_URL` цієї БД, API на 8026 із `WAREHOUSE_COOKIE_SECURE=false`, `WAREHOUSE_CATALOGUE_WORKER_ENABLED=false`; зібраний frontend через `WAREHOUSE_API_PROXY=http://127.0.0.1:8026 npm run preview -- --port 5197`; `WAREHOUSE_E2E=1 WAREHOUSE_STAGE3C_ORIGIN=http://127.0.0.1:5197 node tests/stage3c-browser.mjs`. Fixture містить лише явно синтетичні дані, не очищує попередні донори та не викликає canonical publish endpoint. Початкова canonical reference створюється безпосередньо з pure analyze у порожній локальній fixture-БД; повторні запуски додають тільки нові тестові донори.

Зауваження до локального dev-режиму: наявний App bootstrap під React StrictMode у `vite dev` може залишатися на «Підготовка робочого простору…» через подвійний effect. Browser-приймання виконується на production build/preview, як у deployment; ця попередня поведінка App не змінювалася Stage 3C.

## Підсумкові результати

[verification.json](verification.json): повний backend — **546 passed, 1 skipped** (621,18 с). Після останнього посилення інвалідації stale конфігурації та обробки OEM лише з пробілів — усі **33 Stage 3C тести passed** (121,09 с), включно з відкликанням сесії під час очікування блокування. Frontend — **395 unit tests passed**, TypeScript/Vite build passed. `alembic check`: `No new upgrade operations detected`.

Backend перевіряє 0/1/2/3/5 оголошень, OEM, сторони, двигуни/комплектацію, дати/валюти/стани, latest observations, v1/v2 duplicates, rollback після запису, stale/ABA/replay/concurrent apply, expiry, RBAC/workspace/CSRF, незмінність order/sale snapshots та quantity/reserved. Новий test database upgrade/downgrade guard не видаляє durable decisions.

[Browser results](browser-results.json): production build + локальний реальний API/PostgreSQL, **1440px та 390px passed**, по 227 конструктивних позицій. A/B/C/D відображення, 3 джерела A, ручне збереження/очищення, 409 зі збереженням вводу, bulk preview без запису, окреме підтвердження, discount/rounding, втрачена HTTP-відповідь після commit, reload/status/replay, оцінка та звичайний склад. Залишки/резерви/продані кількості та включення незмінні; receipt/canonical/activation/stock operations не надсилалися браузером. JS-помилок і горизонтального переповнення немає. Усі ціни й OEM цього browser fixture **синтетичні**, не показники Volvo B.

Скриншоти:

| Екран | Desktop | iPhone |
|---|---|---|
| Ринок і власна ціна | [1440](stage3c-prices-1440.png) | [390](stage3c-prices-390.png) |
| Bulk preview | [1440](stage3c-preview-1440.png) | [390](stage3c-preview-390.png) |
| Вартість запчастин | [1440](stage3c-valuation-1440.png) | [390](stage3c-valuation-390.png) |
| Звичайний склад | [1440](stage3c-inventory-1440.png) | [390](stage3c-inventory-390.png) |

[Повний перелік змінених файлів](CHANGED_FILES.txt). Локально готово до контрольованого staging release; deployment і фактичне покриття реального Volvo B потребують окремого приймання. Обмеження: 1000 деталей на атомарну bulk/valuation операцію; 20 000 джерельних mappings на вибірку з безпечним зниженням до C при truncation; немає FX чи автоматично підтвердженого OEM нових virtual Part. Через це новий неперевірений Part зазвичай матиме C/D, доки власник не уточнить факти. Ринок ніколи сам не встановлює його selling_price.

[Перевірка populated upgrade](migration-check.json): окрема синтетична PostgreSQL, `95c3e7b12a04 → a6d94c72e310`, повторний upgrade, `alembic check`; row hashes **усіх 44 попередніх таблиць** незмінні, включно з існуючими залишком 5, резервом 2, ціною 123 та audit. Нові pricing decisions порожні до явних дій.
