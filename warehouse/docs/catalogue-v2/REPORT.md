# Universal Catalogue v2 — результат локального Stage 1–2

## Результат

Реалізовано спільний каталог, platform-owner-only вебімпорт CSV/ZIP v2, адаптер наявного Aleto SQLite/GZIP v1, persisted jobs, preview, ручні зіставлення та явний атомарний apply. Складські записи, власні ціни, фінанси, продажі та аудит не змінюються імпортером. Старий v1 і UX 5.8.1 залишаються сумісними.

База: `9589e5e7bf4b7c694c885ddbdab62f18ea079715`. Backend-коміт: `036fee4b83839051e0a2d52da88cb76089d2934c`. Другий локальний коміт містить UI, readiness compatibility, приклади та цей звіт; його SHA наведено у фінальному повідомленні і доступний через `git log -2`. Обидва коміти — одна майбутня release-одиниця. Push, deployment, staging/production import і Railway Variables не виконувалися.

Архітектура, схема дев'яти нових таблиць, права й activation plan: [README.md](README.md). Формат наступного файла: [FORMAT.md](FORMAT.md). Повний перелік змінених файлів: [CHANGED_FILES.md](CHANGED_FILES.md).

## Перевірки

| Перевірка | Фактичний результат |
| --- | --- |
| Останній повний backend regression | **353 passed, 1 skipped**, 266.05 с; один наявний Starlette/httpx deprecation warning |
| Фінальні Catalogue v2 cases | **26 окремих cases покрито**: 25 були у повному прогоні; після додавання transport-bound case — **25 passed, 1 deselected**, 11.68 с, з великим Volvo case, уже пройденим у повному прогоні |
| Остання перевірка JSON control transport | **2 passed, 24 deselected**, 1.31 с; великі JSON, octet-stream і запити без Content-Type не обходять 4 MiB limit; звичайний preview/apply і binary detection працюють |
| TypeScript + Vite | `npm run build` **успішно** |
| Readiness/frontend units | **187 passed**, невідомі/паралельні heads, хибні contracts/features і flags залишаються заблокованими |
| Global catalogue real-browser | **1440 px + 390 px passed**: upload, preview без запису, reload job, ручне об'єднання, invalidation старого preview, явний apply, shared read |
| Неплатформний DIRECTOR | Меню приховане; direct admin URL закритий; API **403** |
| UX 5.8.1 real-browser | **1440 / 768 / 390 px passed**: графіки, порожні дані, UAH/USD, keyboard selection, Team summaries і navigation |
| Workshop readiness browser | **60 cases + pending/retry на кожному з 3 viewport passed** |
| Старий Plan.Parts browser | **desktop + iPhone passed** |
| Міграція | Єдина head `021e8f6f220c`; additive upgrade/downgrade round-trip зі старими записами пройшов; `alembic check`: **No new upgrade operations detected** |
| Деплой-конфіг/Watch Paths | Обидва наявні локальні check scripts **PASS**, Dockerfile/Variables не змінено |
| Git whitespace/scope | `git diff --check` успішно; зміни лише в `warehouse/` |

Пропущено тільки opt-in Smart Search benchmark на 100 000 рядків. Не підмінено його «успішним» чи нульовим тестовим прогоном. Browser screenshots збережено локально у gitignored `warehouse/frontend/test-results/catalogue-import-v2-{1440,390}.png` та `catalogue-v2-{1440,390}.png`; committed runner відтворює їх.

## Головний Volvo A → B → C

A. Реальний наданий пакет v1 завантажено через новий API-адаптер **лише у локальній тестовій БД**: **7 246 offers, 10 112 applications, 14 400 raw paths**. Український словник v1 збережено; `Комп` явно пропущено як непідтверджене зіставлення, а не вигаданий тип. Canonical part type бере детальну вихідну назву/OEM, не перетворює 101 підкатегорію на весь список типів.

B. Синтетичний інкрементальний CSV містить старе спостереження, нову ціну за новою датою, дві нові пропозиції, нову підкатегорію, неоднозначну назву й відсутню ціну. Після явного вирішення review: **7 248 offers, 7 249 observations**. Синтетична ціна не видається за реальну ринкову.

C. Повтор B після такого самого явного skip: **0 inserts / 0 updates** у всіх глобальних сутностях; кількості незмінні. Історія цін не перезаписується. Перевірено fingerprint усіх початкових таблиць поза `catalogue_*`, включно з непорожнім залишком, резервом, USD-продажем, замовленням, власними цінами, аудитом і legacy Aleto v1 — вони незмінні.

Окремі кейси BMW/Audi додають нові глобальні бренди/моделі. Однаковий OEM не зливає source offers; side/position/OEM і власна назва зберігають різні canonical types. Unicode NFC/casefold не створює дублікати різних записів тієї самої назви. Власник іншого workspace бачить ту саму глобальну пропозицію без повторного імпорту або копіювання.

## Дані, відмови й відновлення

- Preview працює у savepoint з rollback, зберігаючи лише job і звіт. `mode=preview`, `committed=false` перевірені тестом.
- Apply потребує server-side allowlist, активного root DIRECTOR, чинної сесії, CSRF, `confirm=true`, ready job, точного preview token та поточної версії каталогу.
- Історія цін має PostgreSQL UNIQUE і trigger проти UPDATE/DELETE. Суперечлива ціна за тим самим timestamp не переписується.
- Конкурентні застосування одного job ідемпотентні; різним jobs потрібен re-preview після зміни global revision.
- Окремий subprocess аварійно завершено після записів, але до commit: часткових rows немає, job залишається ready, повтор успішний.
- Ручний skip не стирає вже перевірену canonical classification. Якщо відхилено лише зіставлення виробника/моделі, джерельна пропозиція та її ціна залишаються доступними без вигаданого fitment.
- Відхилено ZIP traversal, duplicate entries, symlink, невірні SHA/version/headers, gzip bomb, SQLite views/triggers, invalid prices/timezones/URL. Немає виконання вкладених скриптів чи зовнішніх Aleto-запитів.
- Upload обмежено 16 MiB, expanded payload 64 MiB, ratio 100, 50 000 rows; JSON control body — 4 MiB незалежно від MIME на preview/apply. Перевірений payload живе у PostgreSQL та перевіряється за SHA після перезапуску.

## Наступний файл і наступний реліз

1. Експортер зовнішнього парсера готує CSV/ZIP за [форматом](FORMAT.md), не вигадуючи невідомі роки/OEM/позицію. Приклади [Volvo та BMW/Audi](../../examples/catalogue-v2/README.md) — тільки синтетичні.
2. Після окремого погодження release оператор розгортає обидва локальні коміти як одну одиницю та окремо задає allowlist тільки у Warehouse staging API. У цій задачі цього не виконано.
3. Platform owner завантажує файл через **Адміністрування → Каталог → Імпорт**, перевіряє preview, ціни до/після та pending review; після зміни mapping потрібен новий preview.
4. Лише явне підтвердження цього preview дозволяє apply. Інший DIRECTOR/ADMIN/MANAGER цього зробити не може навіть напряму через HTTP.
5. Усі склади читають результат у **Каталог запчастин → Спільний каталог CarPot v2**. Рекомендованих цін, зміни selling_price або створення реальних деталей немає.

Невирішені/свідомі межі: джерельні title можуть давати надто дрібні canonical types, потрібна курація; немає автоматичного retarget/undo verified aliases; preview синхронний і великі файли можуть перевищити proxy timeout (job зберігається); planner cache для майбутніх значно більших каталогів потребує окремого scale-етапу; роки/VIN/комплектація не верифікуються; алгоритм recommended_price та автоматичне формування stock поза цим етапом. Деталі — у розділі ризиків [архітектури](README.md).
