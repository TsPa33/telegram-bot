# UI-2 — Navigation & Scroll Optimization

База: `9f65de2ad39a86095ec3ceb85ae71e3f5a00d1b8`, `feature/carpot-warehouse-mvp`. Лише frontend shell, його тести та цей звіт. Backend/PostgreSQL/міграції, авторизація/permissions, маршрути й бізнес-обробники не змінені. Push/deployment не виконувалися.

## Причина, встановлена до змін

[DOM/CSS audit](before-audit.json) і screenshots отримано на збірці UI-1 до редагування:

- `.sidebar` — fixed flex-контейнер із `overflow-y:auto` на **всій панелі**. При 1440×600 його `clientHeight=600`, `scrollHeight=740`; при 375×480 — 480/738. Логотип, профіль, навігація й footer були учасниками одного overflow. Меню та його відступи перевищували висоту, а ширину scrollbar визначав браузер (`auto`).
- `.app/.main/main` не є додатковими вертикальними scroll-контейнерами на перевіреній сторінці: основний довгий контент прокручує document. Смуга документа поруч із sidebar — незалежне прокручування, а не другий root-scroll основного вмісту. Глобальний `overflow:hidden` для приховування обох був би помилкою.
- Мобільний shell не блокував body, не виключав фоновий контент із Tab, не мав focus trap/повернення фокуса й явного reveal активного пункту. Це встановлено читанням App/CSS, а не припущенням зі скриншота.

## Виправлення

- `App.tsx`: одна `.sidebar-scroll` обгортка навколо **тих самих** пунктів меню та footer. Логотип/профіль залишаються над нею. NavLink, destinations, permission filters і маршрути збережено. Мобільне меню має доступну кнопку закриття, `aria-expanded/controls`, dialog semantics та `inert` для закритої панелі/відкритого фону.
- `design-system.css`: sidebar не прокручується цілком у звичайних вікнах; тільки меню має `min-height:0`, native overflow, тонкий scrollbar (thin / 6px fallback) з контрастнішим thumb при hover/focus. Scrollbar не вимкнений; wheel, drag, клавіатура й touch залишаються нативними. `overscroll-behavior:contain` обмежує chaining. Footer зберігає нижнє положення, коли вистачає місця.
- `useSidebarScroll.ts` / `sidebarScroll.ts`: активне/сфокусоване посилання розкривається мінімальним зміщенням **лише sidebar scrollport**, без `scrollIntoView` для документа. ResizeObserver враховує зміну висоти. На mobile body фіксується зі збереженням scroll X/Y та компенсацією gutter; після закриття стилі й позиція повертаються. Tab/Shift+Tab утримуються у меню, Escape/кнопка/backdrop закривають його з поверненням фокуса; вибір розділу зберігає чинне auto-close. Desktop resize прибирає lock/inert.
- Нижче 480px висоти зменшено лише вертикальні відступи шапки sidebar. Нижче 280px пріоритет має доступність: прокручується одна вся панель з тонким scrollbar, а внутрішнє меню перестає бути scrollport. Немає двох вкладених scrollbars; active/focus reveal враховує цей fallback.

Таблиці, картки, форми, дизайн-токени та нормальний document scroll не переписані. Намірені внутрішні прокручування dialog/table/спеціальних списків не приховуються глобальними правилами. Header залишається у своєму попередньому normal flow; штучну sticky-шапку не додано.

## Результати

- `npm run build`: **PASS**.
- `node --test tests/*unit.mjs`: **416 passed**, включно з reveal geometry для видимих/обрізаних/завеликих пунктів.
- `WAREHOUSE_E2E=1 node tests/ui2-browser.mjs`: **9 viewport configurations × 9 маршрутів = 81 перевірка**, PASS. Розміри: 1440×900, 1280×720, 768×768, 390×844, 375×812, додатково 1440×600, 1440×320, 375×480 і 375×240.
- Сторінки: Автомобілі, Запчастини UX-1, Склад, Пошук, Продажі, Замовлення, Команда, Статистика, Налаштування. Немає horizontal overflow, додаткового root-scroll у `.app/.main/main` або JS exceptions.
- Перевірено wheel, нативні `touchStart/touchMove/touchEnd` через Chromium CDP, фокус усіх посилань, активний Settings, Tab/Escape/close/backdrop, відсутність зсуву фону, body lock, scroll restoration, auto-close після маршруту й cleanup після resize. Вікна малої висоти також PASS.
- При 1440×600 після змін root sidebar: **600/600**, меню: **388/536**, `scrollbar-width:thin`. При 375×480: root **480/480**, меню **329/526**. При 375×240 працює навмисний один fallback scrollport root. Деталі: [browser-results.json](browser-results.json).

Перевірки локальні, production build/preview + існуючий synthetic fixture. Знімки плану/Part quantity/reserves/prices до/після однакові; сторінки не надсилають stock/catalogue/pricing mutations (batch guidance — read-only POST). Використовується одна звичайна локальна auth-сесія, без зміни auth policy. Backend regression не запускався. Фізичний iPhone/Safari та Railway у цьому завданні не тестувалися.

## Скриншоти

| Вікно | До | Після |
|---|---|---|
| Desktop 1440×600 | [UI-1](before-1440-600.png) | [UI-2](sidebar-1440-600.png) |
| Mobile 375×480 | [UI-1](before-375-480.png) | [UI-2, меню прокручено](sidebar-375-480.png) |

Інші після: [1440](sidebar-1440-900.png), [1280](sidebar-1280-720.png), [768](sidebar-768-768.png), [390](sidebar-390-844.png), [375](sidebar-375-812.png), [низький desktop](sidebar-1440-320.png), [240px height fallback](sidebar-375-240.png). На mobile фон збережено на попередній позиції прокручування; зміщення фонового вмісту на порівняльних знімках не є зміною макета.

[Перелік файлів](CHANGED_FILES.txt). Локальний SHA: `git log -1 --format=%H -- warehouse/docs/ui-2`. Публікація потребує окремого дозволу.
