# Warehouse v2.3 — Mobile Search & Checkout

Branch: `fix/warehouse-mobile-search-v23`.
Base: PR #516, `13fd0cc81d51f02e4c37d8408b8abc40de54c865`, `feature/warehouse-mobile-search-checkout`.

## Причини та виправлення

- `SalesWorkspace.tsx` виключав mobile з `optionsOpen`. Тепер підказки з чинного parts/smart-search API працюють також на мобільному, debounce 300 мс збережено. `useLoad` і query-key відкидають застарілі відповіді; UI додатково звіряє введений та застосований запит. Немає додаткового autocomplete API.
- Порожній мобільний пошук більше не завантажує та не показує весь склад. Введення під час debounce також не запускає порожній запит. Явний вибір фільтра дозволяє перегляд відповідної вибірки. Desktop зберігає чинний список.
- Компактне поле: пошукова іконка, очищення, підказки без кнопки «Знайти». Фільтри, режим і категорії — один допоміжний ряд. Підказки розташовані у звичайному потоці, без перекриття результатів абсолютною панеллю.
- Blur поля міг прибрати підказки та пересунути картку між pointerdown/click. Натискання кнопок мобільної картки тепер не змінює розкладку до обробки tap; відкриття деталей/checkout явно знімає фокус.
- Назва — 18px та головний акцент; нижче авто/рік, OEM/артикул, наявність, ціна. Фото 32px. Прибрано дубль «Деталі запчастини»; назва відкриває quick preview, компактна кнопка — чинний OrderComposer. Другорядні операції збережені в меню.
- `mobile-checkout-footer` мав sticky positioning. На mobile він тепер статичний, після товарів, покупця, доставки й вибору дії. Один вертикальний scroll у dialog; вкладені результати picker/buyer більше не створюють окремих scroll areas. Desktop layout не замінено.
- `useKeyboardViewport` слухає реальний `visualViewport.resize`, обмежує висоту мобільного dialog доступною висотою та прокручує закрите активне поле. Фон checkout заблокований від прокручування; cleanup відновлює його.
- Order picker автоматично шукає чинним API, перевіряє ключ відповіді (запит/донор/сторінка), після вибору закривається. Фільтр донора на mobile згорнутий. Стан кошика/покупця/доставки залишається в існуючому composer.
- Buyer picker показує результати за телефоном, loading/empty/error/retry. Новий покупець створюється лише через явне відкриття форми й підтвердження. Застарілі результати приховані за ключем телефону/сторінки; uncertain-create guard збережено.
- Запит пошуку зберігається в sessionStorage користувача та відновлюється після переходу до замовлення й назад. При забороненому storage форма продовжує працювати.

Backend/API, schema/migrations, import-worker, stock algorithms, money calculations, RBAC та idempotency не змінювалися. Railway/production/staging не використовувалися.

## Перевірки

| Перевірка | Результат |
|---|---|
| Frontend prebuild | 275 PASS |
| TypeScript та production build | PASS; стандартне попередження Vite про bundle >500kB залишається |
| Backend `tests/test_orders.py` | 25 PASS, окрема PostgreSQL 16 `warehouse_mobile_v23_regression_test` на localhost:55441 |
| Новий real-auth Chromium E2E | PASS на 320 / 390 / 430 / 1440 |
| Попередній mobile-search-checkout suite | PASS; очікування оновлено під автоматичний пошук і відкриття за назвою |
| Corporate UX suite | PASS: sidebar, picker, themes, sales lifecycle, buyer history та 1440/1920/390 |
| WebKit / фізичний iPhone | UNVERIFIED: завантаження WebKit повернуло 403 `Domain forbidden` |

Новий E2E використовує справжні cookie/CSRF, локальні API та PostgreSQL `warehouse_mobile_v23_browser_test`. Створює лише синтетичні дані окремого workspace для кожної ширини. Injected cases — затримка справжньої відповіді та помилка читання buyers (503), без підміни успішних stock/auth/checkout результатів.

Перевірено:

- підказки без submit; назва, OEM, артикул;
- відсутність unfiltered request при порожньому вводі/очікуванні debounce;
- затримана попередня відповідь не стирає поточний OEM-результат;
- ім'я товару більшим шрифтом за ціну; прямий tap із відкритими підказками;
- phone search: empty, error/retry, вибір; форма нового покупця тільки після явного натискання;
- додавання другого товару не губить кількість, ціну, покупця, місто й відділення;
- статичний підсумок після контенту, без horizontal overflow;
- reserve exact replay не подвоює резерв; продаж списує товари один раз; повторний sell повертає 409, історія продажу містить рівно дві операції для двох позицій;
- повернення з замовлення до пошуку з тим самим запитом; очищення;
- all palettes (Day/Onyx/Midnight Gold/Forest Slate), JS errors = [];
- зменшений viewport висотою 430px для пошуку, телефону, picker та кінця checkout.

**Скриншоти `*-keyboard.png` показують симуляцію зменшеної доступної висоти, а не фізичну клавіатуру iOS.** Реальний iPhone/Android із системною клавіатурою залишається staging/device acceptance. Не заявляємо локальний Chromium за iOS-тест.

## Порівняння з базою

Один і той самий локальний API, workspace і тестовий товар, ширина 390. Базовий код без змін у detached worktree, Vite dev; v2.3 — production preview. Це layout-порівняння, **не benchmark мережі чи часу виконання**.

| Вимір | Base PR #516 | v2.3 |
|---|---:|---:|
| Верх поля пошуку | 182.17px | 115px |
| Верх першого результату | 574.27px | 259.39px |

Перший товар приблизно на **315px вище**. Базовий код уже автоматично оновлював основні результати; виправлення додає відсутні мобільні підказки й прибирає зайвий візуальний submit. Штучного твердження «пошук став швидшим на N мс» немає.

## Файли

- `frontend/src/PartsSearchControls.tsx`
- `frontend/src/SalesWorkspace.tsx`
- `frontend/src/Orders.tsx`
- `frontend/src/useMobileSearch.ts`
- `frontend/src/mobile-search-checkout.css`
- `frontend/tests/mobile-search-v23-unit.mjs` — viewport tracking, obscured focus, listener/timer cleanup.
- `frontend/tests/mobile-search-v23-browser.mjs` — чотири ширини, реальні reserve/sale.
- `frontend/tests/mobile-search-v23-comparison.mjs` — опційне локальне layout-порівняння.
- `frontend/tests/mobile-search-checkout-browser.mjs`, `frontend/package.json`.
- `.github/workflows/warehouse-corporate-ux-v2.yml` — Chromium і WebKit V23 suites на disposable localhost PostgreSQL. CI WebKit ще не підтверджений запуском GitHub Actions.
- Цей документ, `screenshots/`, JSON browser reports.

## Відтворення

1. Лише disposable локальна PostgreSQL з назвою `warehouse*_test`; жодних Railway URL. Backend tests TRUNCATE цю БД.
2. Backend: `WAREHOUSE_TEST_DATABASE_URL=<local dedicated test URL> python -m pytest tests/test_orders.py -q`.
3. Frontend: `npm ci && npm run build`.
4. Окремий browser DB, штатні Alembic міграції **тільки локально**, API app на 8080 з `WAREHOUSE_ENV=local`, `WAREHOUSE_COOKIE_SECURE=false`, registration enabled, worker/Plan.Parts disabled. Preview: `WAREHOUSE_API_PROXY=http://127.0.0.1:8080 npm run preview -- --host 127.0.0.1 --port 5280 --strictPort`.
5. `WAREHOUSE_E2E=1 node tests/mobile-search-v23-browser.mjs` (Chromium або `WAREHOUSE_CHROMIUM_PATH`). WebKit: встановити штатний Playwright WebKit і додати `V23_ENGINE=webkit`. Origin допускає тільки localhost:5280/5260.
6. Comparison додатково потребує незмінену базу PR #516 на localhost:5290 із тим самим локальним API. Запуск: `WAREHOUSE_E2E=1 node tests/mobile-search-v23-comparison.mjs`.

## Staging acceptance — після окремого дозволу

- Не merge/deploy автоматично. Спочатку Draft PR до `feature/warehouse-mobile-search-checkout`.
- На тестовому workspace перевірити всі сценарії на 320/390/430/1440, включно з реальною цифровою клавіатурою iPhone/Android, rotation та browser chrome.
- Пошук → підказка/картка → checkout; покупець → додавання товару → повернення до кошика → резерв → продаж. Звірити дві sale operations і відсутність повторного списання.
- Перевірити довгі назви/OEM, всі теми, мережеві помилки, RBAC та відновлення запиту.
- Реальні складські залишки не використовувати для QA.

## GitHub

Git transport працює. GitHub API у поточному середовищі повертає `Forbidden`; автоматичне створення Draft PR недоступне. Після push відкрити compare зазначених гілок через авторизований GitHub і вибрати **Create draft pull request**. Не вважати compare link уже створеним PR.
