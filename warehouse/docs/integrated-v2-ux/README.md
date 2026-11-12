# Integrated v2 — точкові UX-покращення

Гілка: `fix/warehouse-integrated-v2-ux`.
База: `185a1aef2e958521fad75bc8ef305c8b4ecef58c`, `feature/warehouse-508-integrated-v2` (PR #512).

## Зміни

1. Оновлено існуючу Midnight Gold, додано Forest Slate через спільні токени `themes.css`. Emerald прибрано з вибору та runtime-палітр; старе збережене значення безпечно відкриває Forest Slate. Onyx і світла тема доступні. Bootstrap і React використовують однакове правило, включно з недоступним localStorage.
2. Узгоджено поверхні sidebar/content, межі, primary/hover/focus, semantic text; структура Integrated v2 збережена. Виправлено мобільний перемикач та його розташування.
3. Швидкий перегляд має спільний рядок заголовка, навігації, лічильника й закриття без absolute-перекриття; мобільний dialog збережено.
4. Зменшення кількості: Продано / Дефект або несправність / Інша причина / Пропустити. Інша причина вимагає тексту. Пропустити не потребує введення, але передає явний системний опис у чинну операцію й журнал. Ідемпотентний повтор запиту не змінено.
5. **Продано не виконує write_off.** Відкривається чинний OrderComposer із кількістю зменшення; списання та виручка проводяться існуючим checkout лише після підтвердження продажу. Збереження чернетки не є продажем. Для користувачів без orders.create/inventory.view цей варіант недоступний. Підтвердження фактичного складу вузлів виконує існуючий редактор.
6. Додано явну заміну товару через компактний picker. Заміна створює новий line draft без перенесення чужих цін/assembly-token; дублікати не дозволені. Додавання, кількість, ціна, валюта та видалення використовують чинний редактор. Зарезервоване замовлення використовує наявний атомарний revise-reserved з явним підтвердженням; проведений продаж не редагується як відкритий резерв.
7. Аналітика більше не займає один трек прихованої триколонкової сітки: повна ширина, KPI фактичних продажів, адаптивні графіки. Валюти не підсумовуються, виручка не називається прибутком.
8. Повернення до замовлень/центру продажів та існуюча back-кнопка мають chip/ghost presentation, іконку, 44px hit area і focus. Маршруту «Усі оголошення» в цій базі немає; новий функціонал оголошень не створювався.

## Основні файли

- `frontend/src/Theme.tsx`, `frontend/index.html`, `frontend/src/themes.css`: палітри, bootstrap, preference migration.
- `frontend/src/integrated-ux-polish.css`, `frontend/src/theme-surfaces.css`, `frontend/src/main.tsx`: спільні стани й геометрія.
- `frontend/src/InventoryQuantity.tsx`, `frontend/src/quantityReason.ts`: причини й перехід у checkout.
- `frontend/src/Orders.tsx`: заміна позиції, навігація.
- `frontend/src/SearchPartPreview.tsx`: заголовок перегляду.
- `frontend/src/SalesCenter.tsx`, `frontend/src/SalesTrend.tsx`: ширина аналітики/KPI.
- `frontend/tests/integrated-ux-unit.mjs`, `frontend/tests/integrated-ux-browser.mjs`, `frontend/package.json`: цільові перевірки.
- `.github/workflows/warehouse-corporate-ux-v2.yml`: запуск нового authenticated browser suite після існуючого integrated suite на disposable PostgreSQL.

Production API, backend-код, схема, міграції, import worker і бізнес-алгоритми резервування/продажу не змінювалися.

## Локальна перевірка

- Backend `tests/test_orders.py`: **25 PASS**. Окрема PostgreSQL 16, `127.0.0.1:55441/warehouse_integrated_ux_regression_test`. Перевірено rollback резервів, повтори, конкурентні дії та заборону revise після продажу.
- Frontend prebuild: **273 PASS**, TypeScript + production build PASS. Залишилося попередження Vite про chunk >500 kB; code splitting поза цим завданням.
- Playwright Chromium: справжні локальні реєстрація, cookie/CSRF, API та PostgreSQL. База `warehouse_integrated_ux_browser_test`, API 8070, production preview 5270. Без fixtures замість auth/stock/order API.
- E2E: всі чотири причини; журнал списання; оформлення одного продажу через checkout; відсутність передчасного списання; зміна зарезервованого замовлення (заміна, додавання/видалення, кількість, ціна), звільнення старого резерву й новий резерв без зміни quantity; обидві палітри, desktop 1440/mobile 390, quick preview, sidebar collapse, ширина аналітики, порожні JS errors.
- Чинний `corporate-ux-v2-browser.mjs`: PASS — aligned sidebar collapse/hover/expand, picker, theme reload (Forest/Onyx/Gold), 1440/1920/390, sales lifecycle і exact buyer history. Замінено тільки застарілий selectable Emerald у тесті на Forest, додано параметри локального origin/Chromium.
- AA контраст основного/другорядного тексту та підпису primary перевіряється з фактичних токенів обох палітр.

Скриншоти та JSON у `screenshots/` містять **лише синтетичні локальні записи**, це не staging acceptance.

Запуск frontend: `npm ci && npm run build`.
Запуск browser: `WAREHOUSE_E2E=1 node tests/integrated-ux-browser.mjs`; потрібні API 8070 на disposable localhost PostgreSQL та `WAREHOUSE_API_PROXY=http://127.0.0.1:8070 npm run preview -- --host 127.0.0.1 --port 5270 --strictPort`.
У CI suite повторно використовує захищений `dismantling_v2_browser_server` і окрему тестову БД існуючого job; origin задається `UX_POLISH_ORIGIN=http://127.0.0.1:5260`. Зовнішні origin заборонено.

## Staging acceptance — тільки після окремого погодження

1. Переглянути diff від зазначеної бази; не переносити PR автоматично до іншої staging-гілки.
2. Після дозволеного розгортання перевірити Midnight Gold, Forest Slate, Onyx і День; перезавантаження, міграцію старого Emerald, мобільний topbar та sidebar.
3. Перевірити quick preview: попередня/наступна, лічильник, закриття, desktop/mobile, довгі назви.
4. В ізольованому тестовому workspace: зменшення з дефектом/іншою причиною/пропуском має залишати журнал. Продано має відкрити оформлення, а не списувати негайно; перевірити виручку й рівно одне списання після підтвердження.
5. У тестовому чернетковому/зарезервованому замовленні додати/замінити/видалити позиції, змінити кількість і ціну; перевірити резерви та reload. Недостатній залишок має відкотити всю зміну. Проведений продаж не повинен мати довільного редактора позицій.
6. Перевірити KPI, фільтри й повну ширину аналітики, навігаційні chip-кнопки.

Staging/production, реальні залишки та платні API не використовувалися. Deployment не виконувався.

## Публікація

Git transport доступний; GitHub API у цій сесії повертає `Forbidden`. Автоматичне створення Draft PR заблоковане саме API-доступом. Після push відкрити compare до `feature/warehouse-508-integrated-v2` і вибрати **Create draft pull request**; не merge та не deploy без окремого погодження.
