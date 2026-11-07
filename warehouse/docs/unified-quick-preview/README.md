# Єдиний швидкий перегляд запчастин

## Реалізація

`SearchPartPreview.tsx` повторно використовується в пошуку, складі та розборі. `QuickPreviewFrame.tsx` відповідає лише за контейнер, закриття, keyboard/focus і mobile drawer; бізнес-дії залишаються в чинних контролерах сторінок.

- Вільна область рядка та Enter/Space відкривають перегляд. Checkbox, quantity, посилання і кнопки виключені з делегування. «Дії» відкриває тільки native popover; Escape меню не закриває панель одночасно.
- Close / Escape / клік поза таблицею і панеллю закривають перегляд. Видалено fallback на першу запчастину, що заважав повному закриттю.
- Desktop: права панель зі sticky контейнером та незалежним scroll у доступній частині viewport. Mobile ≤900px: native modal drawer, focus containment, блокування фону та відновлення фокуса/scroll після закриття. Вужчий desktop використовує адаптивні картки.
- Панель показує фактичні назву, фото або placeholder, донора, категорію, статус, залишок і резерв, OEM, артикул/виробника, власну ціну з оригінальною валютою.
- Продаж доступний у складському/пошуковому контексті лише для придатного доступного залишку. OEM, ціна, нотатки, перевірка та картка використовують чинні permission-guarded компоненти й endpoints. Локації в панель не повернуті.
- Каталожна позиція без фізичної картки показує «Не на складі»; не отримує вигаданого залишку або продажу. Додавання 1 шт. і зміни плану — лише явними діями через існуючі операції. За кількох карток можна вибрати конкретну для перегляду.
- Склад має 5 колонок: запчастина з підписом донора, залишок, OEM/артикул, ціна, дії. Пагінація, CSV, фільтри та вибір збережені. Таблиця розбору не отримала OEM/артикулів.
- У пошуку категорії стоять над фільтрами; компактний ряд «Усі» + 4 системи + «Ще категорії». Класифікація та підгрупи збережені, числа з макетів не використовуються.

## Дизайн

Розширено існуючі `tokens.css`: корпоративний font stack, обмежена типографічна шкала й семантичні row colors; `style.css` споживає цей самий font token. `part-corporate.css` обмежено трьома контекстами та спільною панеллю. Primary/secondary/ghost/destructive/focus/disabled використовують чинну систему.

Виправлено обрізання «Дії», перенесення quantity-кнопок, накладання старого sticky footer панелі на фото/дані, різні розміри тексту й конфлікт `.empty` зі статусом нульового залишку. Кнопки мають сенсорні області 44px.

## Перевірки

- `npm run build`: PASS, включно зі штатним prebuild (217 PASS). Фінальні `tsc -b && vite build`: PASS; збережено стандартне попередження Vite про chunk size.
- `node --test tests/quick-preview-unit.mjs tests/stock-compact-unit.mjs tests/inventory-presentation-unit.mjs tests/part-row-unit.mjs`: **21 PASS**. Зокрема поведінкові перевірки click/keyboard callback без DOM-залежних snapshot assertions.
- `WAREHOUSE_E2E=1 node tests/quick-preview-browser.mjs`: **PASS**, Chromium, 1440/1100/390px, окрема локальна тестова PostgreSQL та guarded mock provider.
- Перевірено три контексти, один перегляд, перемикання записів, independent checkbox/quantity, меню/Escape, close без повторного відкриття, native focus trap і scroll restore, notes dialog поверх preview, реальні локальні price/OEM updates, явне add-one, синхронізацію між сторінками, відсутність overflow і обрізання «Дії».
- Browser JS errors: **0**. Реальних платних API-викликів: **0**. Складські й цінові зміни стосувалися лише локальних synthetic fixtures.

Актуальне browser-приймання нової поведінки: `quick-preview-browser.mjs`. Історичний `part-row-browser.mjs` перевіряв попередню поведінку «клік рядка → меню» та не є критерієм нового UX.

[Склад desktop](screenshots/inventory-1440.png) · [Склад mobile](screenshots/inventory-390.png) · [Пошук desktop](screenshots/search-1440.png) · [Пошук mobile](screenshots/search-390.png) · [Розбір desktop](screenshots/donor-1440.png) · [Розбір mobile](screenshots/donor-390.png)

## Межі й release

Backend, PostgreSQL schema/migrations, paid API flow, нормалізація, складські та фінансові правила не змінені. Автоматичний OEM endpoint не додано. Наявність фотосховища визначає чинний backend; за відсутності фото показано placeholder. Навігація панелі стосується завантажених результатів/плану.

Очікується Web Auto Deploy після звичайного push feature-гілки; ручний deployment не потрібний. Railway-інструмент у цій сесії недоступний: фактичні deployment та staging QA — UNVERIFIED. Production/staging-дані не змінювалися.
