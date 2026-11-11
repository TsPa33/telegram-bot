# PR1 — підготовка контрольованого staging acceptance

Дата: 11.11.2026 (Europe/Kyiv). Issue #490.

## Git і PR

- Код PR1 незмінений: `a109bc5ce4162e681aefa3a12429793b36d21bb0`.
- База: `be6448a1d705a3617cdf5b6f46cd095f1b3bb554`, `feature/assembly-component-inventory`.
- Окрема опублікована гілка: `review/warehouse-vin-to-stock-pr1`. Наступний commit додає тільки цей checklist і логи; runtime-код залишається a109bc5.
- Прямого push у shared staging/main не виконано. Remote staging залишився be6448a; read-only snapshot main: `2691e92f497d207fc0b903a1612478a327133849`.
- Diff перевірено: runtime зміни тільки `/warehouse`, без Alembic, requirements, Dockerfile, startup, Variables чи service configuration. Нової архітектури/генератора/ledger немає.
- Створення Draft PR через офіційний GitHub REST API `POST /repos/TsPa33/telegram-bot/pulls` повернуло **Forbidden**. Номер PR не отримано, створення PR не підтверджене. Повторний POST не виконувався.
- [Створити PR з правильною базою](https://github.com/TsPa33/telegram-bot/compare/feature/assembly-component-inventory...review/warehouse-vin-to-stock-pr1?expand=1). Base обов'язково `feature/assembly-component-inventory`, head `review/warehouse-vin-to-stock-pr1`; не main. Обрати Draft перед створенням.

Пропонований title: **Warehouse PR1: connect VIN donors to exact catalogue and bulk stock**.

Опис для PR: VIN-created donor отримує явне підтвердження exact Catalogue IDs без створення другого автомобіля. Чинні category selection, physical confirmation, GuidedReceipt і resumable batches знову підключено до поточного екрану. Збережено один Part/Operation ledger, request-key replay, workspace/CSRF/RBAC, старі плани й складські зв'язки. Не додано автоматичного VIN→TecDoc inference, PRD publish або міграцій. Review перед будь-яким merge/Auto Deploy; staging acceptance ще NOT VERIFIED.

## PASS/FAIL по переходах

**Усі наведені PASS локальні. Жоден не є staging PASS.**

| Перехід / інваріант | Локально | warehouse-staging |
|---|---|---|
| VIN → декодер → редагування → той самий donor | PASS, два контрольні VIN у fixture adapters | BLOCKED: доступ відсутній; live провайдери не перевірені |
| Donor → точна модифікація | PASS, явний вибір source IDs/SHA, не автоматична VIN-ідентифікація | UNVERIFIED: фактичний directory/approved source graph невідомий |
| Модифікація → partial source plan | PASS, pinned synthetic source fixture | UNVERIFIED |
| Немає точного джерела/токенів → загальний каталог | PASS, 4 конфігурації, PLAN_PARTS_ENABLED=false, ключ порожній | UNVERIFIED |
| Каталог → вибір категорії / усіх відфільтрованих | PASS browser + наявні 9 batch/selection unit tests | UNVERIFIED |
| Вибір → presence/dismantled → масове надходження | PASS browser, exact selected IDs, інша категорія не надходить | UNVERIFIED |
| Надходження → склад після refresh | PASS browser, один Part/quantity1 | UNVERIFIED |
| Повтор/новий request key/concurrent receipt | PASS, one receipt; stale409 або already-received skip | UNVERIFIED |
| Інша марка | PASS Renault у VIN fixtures; Golf/ZOE у загальному generator | UNVERIFIED: не видається за live source availability |
| Старі плани/склад/резерви/sale history/physical memberships | PASS targeted regressions; не переприв'язуються автоматично | Не читали й не змінювали робочі staging записи |

Додатковий release gate: **13 backend PASS** — VIN-to-stock, старі плани/ціни/резерви/історія, orders reserve/release, parent-child concurrent sale, одна виручка, replay/return, concurrent receipt. [Лог](vin-stock-release-evidence/pr1-release-acceptance-tests.txt).

Безтокеновий gate: **4 PASS** — Volvo XC60, XC90, Volkswagen Golf, Renault ZOE, без зовнішнього exact source lookup/paid requests; регенерація без нових рядків і без Part до явного надходження. [Лог](vin-stock-release-evidence/pr1-no-token-tests.txt).

Повторний browser 1440/390: **PASS**, VIN→той самий donor→source selection→категорія→receipt→reload; без overflow/JS errors/paid calls. **Синтетичні локальні адаптери**, не live VIN/source proof. [Лог](vin-stock-release-evidence/pr1-release-browser.txt).

Попередні результати a109bc5: 23 backend PASS, 9 frontend batch tests PASS, TypeScript/Vite build PASS — збережені в [аудиті](VIN_TO_STOCK_AUDIT.md). Runtime код після цих перевірок не змінено, повний suite не повторювався.

## Контрольоване розгортання — готовий порядок, НЕ виконано

1. Створити та переглянути вказаний PR. До схвалення не merge, не push у shared staging, не міняти source branch сервісів і не запускати deployment.
2. Через авторизований Railway підтвердити target **selfless-caring / warehouse-staging**:
   - project `ff2f3a14-2ffa-49ba-9b9d-9889ce98da5d`;
   - environment `e9d04365-fc5a-4ba2-84a7-275c44580fe8`;
   - API `telegram-bot`, ID `d9d632a7-5829-4093-a07b-2d9de1f4cd53`;
   - Web `confident-sparkle`, ID `fb258580-75b1-40eb-b0a6-3cf271438639`.
   Це owner-provided IDs з попереднього контексту; actual bindings/deployed SHAs/ізоляція в цій сесії **UNVERIFIED**. Перевірити окрему PostgreSQL та томи, не читати production.
3. PR1 не має міграцій; packaged head залишається **08b72c9d4e16**. Read-only перевірити фактичний staging alembic_version. За розбіжності STOP для compatibility assessment, не downgrade/повторна ручна міграція. API вже використовує штатний `python -m app.staging` → migration lock/startup; не додавати другий запуск.
4. Звірити чинні root `/warehouse`, API Dockerfile `deploy/railway/backend.Dockerfile`, Web `deploy/railway/frontend.Dockerfile`, branch/watch patterns. Не змінювати Variables/worker/Catalogue MySQL для цього PR. Увімкнення ASSEMBLY_INVENTORY_ENABLED не потрібне базовому VIN→stock.
5. Після схвалення PR — звичайна інтеграція через PR у shared staging source branch і її штатний Auto Deploy. Цей крок **ще не дозволено вважати виконаним**. Розгорнути API/Web на одному reviewed merge SHA, що містить a109bc5. Якщо base зміниться, перевірити diff і ancestry до інтеграції. Не створювати нові Railway environments/services. Не змінювати production/worker.
6. Підтвердити API/Web SUCCESS, фактичний SHA обох, API startup logs без migration/runtime помилок, `/health`200, Web/login доступні. Один HTTP200 без SHA не підтверджує реліз.
7. Створити/використати **окремий QA workspace**, не реальний робочий donor. Зафіксувати initial counts/receipts/reserves/sales цього workspace. Виконати два контрольні VIN live; записати реально повернуті й невідомі поля, явно вибрати доступну точну модифікацію без fuzzy inference. Не присвоювати car_id107555 довільному VIN. Якщо source недоступний — окремо перевірити безплатний загальний каталог із чесним coverage.
8. Для source pilot використати наявні перевірені part-зв'язки, partial дозволений. Не чекати нормалізації всіх 2184. 2184 PRD/60098 modifications не оголошувати runtime catalogue; нових owner-approved PRD все ще0. Якщо в directory немає потрібної reviewed модифікації, exact source case залишається UNVERIFIED; baseline case можна перевірити незалежно.
9. Категорія → вибрати все відфільтроване → present → dismantled → перевірити quantity/location/price → explicit receipt. Refresh → ті самі Part. Повторне додавання/timeout replay → без дубля; кількість receipt operations не збільшується вдруге. Перевірити сторонню марку на фактично доступних даних або явно ручному QA авто, не вигадувати live VIN/source fitment.
10. Не виконувати реальні продажі/складські зміни поза QA workspace. Після acceptance звірити старі робочі дані SELECT-only, без перезапису. Ціни/резерви/історію старих позицій не змінювати. Для старих fallback/legacy планів source rebinding409 — очікуваний захист, потрібен окремий preview/resolution, не delete/rebuild.
11. Якщо API/Web не стартує — зібрати logs; PR1 не змінює схему, можливе повернення попереднього application SHA після compatibility check. Жодного downgrade/drop/очищення даних.

## Фактичні зовнішні блокери й наступна дія

- **GitHub PR API Forbidden:** branch push успішний, PR number відсутній. Потрібне створення/перегляд Draft PR через вказаний compare URL або авторизований GitHub API. Це не проблема Git ancestry чи функціонального коду.
- **Railway CONNECT403:** одна спроба API health повернула CONNECT tunnel failed403, HTTP status000; Railway tool/CLI/авторизованого браузера в сесії немає. Не повторювали й не обходили. Потрібен авторизований Railway для перевірки ізоляції/config та наступного deployment/QA.
- Немає підтвердженого live exact source directory. Це окремий data-verification case, не причина блокувати baseline 216/227 pilot до review всіх2184.

**Кодових FAIL у виконаних перевірках немає. Нових функціональних виправлень у цьому етапі не внесено. Deployment НЕ виконаний. Статус: REVIEW BRANCH PUBLISHED / PR CREATION BLOCKED / STAGING ACCEPTANCE BLOCKED. PR2 UI не починаємо, доки реальний functional acceptance не PASS.**
