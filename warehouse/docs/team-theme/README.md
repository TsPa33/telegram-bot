# Команда та глобальні теми

- «Команда»: ролі й єдиний список угорі, шість фактичних KPI, чотири плитки дій, журнал доступів. Графік за 7 днів видалений із frontend. Фільтри працюють з основним списком поточної серверної сторінки. `last_login_at` не замінюється датою аудиту. Клік/Enter/Space відкриває чинне керування дозволеним працівником або read-only картку. Форми, readiness, grantable permissions, заборони саморедагування/підвищення ролей та backend endpoints збережені.
- Один `ThemeProvider` і один `ThemeSwitch` у глобальній шапці. День/Ніч зберігаються в localStorage; без збереженого вибору використовується системна тема та її зміни. Є синхронізація вкладок браузера й fallback при недоступному localStorage. Inline bootstrap до module/CSS застосовує початкову тему без очікування React. Запитів зміни теми до backend немає.
- `themes.css` перевизначає чинні семантичні токени. `theme-surfaces.css` — автоматично згенерований нічний адаптаційний шар старих літеральних кольорів; не змінює geometry або денні декларації. Відтворення: `node scripts/generate-theme-surfaces.mjs`. Явні dark overrides після нього прибирають декоративний світлий градієнт і зберігають графітовий sidebar. Два inline-кольори в PlanPartsBatch переведено на наявні токени.

## Перевірки

- `node --test tests/theme-day-night-unit.mjs tests/theme-unit.mjs tests/team-unit.mjs`: **89 PASS** — preference/fallback/bootstrap, AA semantic color pairs, існуючий readiness/permissions contract.
- `npm --ignore-scripts run build`: **PASS**. Штатний prebuild (217 тестів) пройдено під час початкової збірки; незмінний hook повторно не запускався. Залишається стандартне попередження Vite про розмір chunk.
- `WAREHOUSE_E2E=1 node tests/team-theme-browser.mjs`: **PASS**, 40 route/theme/width комбінацій (1440/390px), окремі перевірки налаштувань деталей, night popover/QuickPreview/drawer, Escape/focus/scroll, збереження теми після reload та системного fallback.
- Перевірені маршрути: команда, пошук, автомобілі, розбір, склад, продажі, замовлення, статистика, каталог admin, налаштування. Відсутні JS errors і horizontal overflow. Жодних платних API-викликів або складських/фінансових операцій. `/pricing/guidance` є чинним read-only POST до імпортованих даних; він не є записувальною операцією.

[День desktop](screenshots/team-light-1440.png) · [Ніч desktop](screenshots/team-dark-1440.png) · [День mobile](screenshots/team-light-390.png) · [Ніч mobile](screenshots/team-dark-390.png) · [Ніч: склад і меню](screenshots/inventory-dark.png) · [Ніч: drawer](screenshots/drawer-dark.png)

## Межі

Локальний synthetic account не має platform-owner доступу: на admin-маршруті перевірено захищений стан, а не повний owner-only контент. У локальному readiness створення співробітників вимкнено; записувальні сценарії команди не виконувалися. Заповнені фінансові графіки та staging приймаються окремо. Окремих зображень-референсів Команди/Дня–Ночі у цьому повідомленні немає: компонування виконане за текстовою специфікацією та чинним корпоративним стилем.

Backend, migrations, PostgreSQL, permissions, Plan.Parts, ціни, залишки, продажі та фінансові правила не змінені. Railway у цій сесії недоступний: deployment/staging QA — UNVERIFIED; очікується лише Web Auto Deploy після звичайного push.
