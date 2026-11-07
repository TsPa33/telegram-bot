# Інтерактивні рядки й залишки

## Реалізація

- Спільні `partRowInteraction.ts` та `part-table-interaction.css`: вільна область рядка відкриває його меню; Enter/Space, zebra, hover, selected, active та видимий focus. Checkbox, кнопки, посилання, поля й меню виключені з делегованого кліку.
- `PlanPartActions.tsx`: контекстні дії плану за фактичним статусом і permissions. Native auto-popover у top layer: одне відкрите меню, outside click, Escape, клавіатурні стрілки, розміщення вгорі/внизу та відстеження scroll/resize. Наявний `PartActionMenu.tsx` для складу/пошуку зберігає власні дозволені бізнес-дії та використовує той самий контракт кнопки «Дії».
- `DismantlingBoard.tsx`: збалансовані колонки, фактичні картки залишку, явне «Не на складі», чинне пакетне додавання 1 шт. Для кількох карток відображаються окремі контроли без змішування їх залишків.
- `InventoryQuantity.tsx` повторно використовується в усіх трьох таблицях: receipt +1, write_off −1 з обов'язковою причиною, correction через натискання числа. Наявні server operations, permissions, резервування, request_key і retry зберігаються. Зміна розсилає наявну `warehouse:inventory-changed`.
- `InventoryPartsList.tsx` та `SalesWorkspace.tsx`: спільна взаємодія рядка; старий зовнішній role=button у пошуку прибрано, щоб не поєднувати відкриття preview та меню. Preview залишається через назву/окрему кнопку. Backend не змінений.

## Перевірки

- `npm run build`: PASS (штатний prebuild: 217 PASS); після фінальних правок `tsc -b && vite build`: PASS. Є стандартне попередження Vite про великий chunk.
- `node --test tests/part-row-unit.mjs tests/parts-tabs-unit.mjs tests/vehicle-workspace-unit.mjs tests/catalogue-stabilization-unit.mjs`: **24 PASS**.
- `WAREHOUSE_E2E=1 node tests/part-row-browser.mjs`: **PASS**. Окрема локальна тестова PostgreSQL, guarded mock provider, синтетичний донор. Перевірені: row click, checkbox/quantity isolation, одне меню, outside/Escape, Enter/Space, zebra, +1, correction, write-off з причиною, audit receipt/correction/write_off, повтор того самого add-batch без дублікатів, reload, заборона correction нижче резерву, disabled write-off при повному резерві, меню складу/пошуку, 1440px/390px, відсутність overflow і JS errors.
- Реальних платних Plan.Parts-запитів: **0**. Тестові зміни залишків виконано тільки в локальному synthetic workspace.

Скриншоти: [розбір desktop](screenshots/donor-1440.png), [розбір mobile](screenshots/donor-390.png), [склад](screenshots/inventory-1440.png), [пошук](screenshots/search-1440.png). Числа й авто синтетичні.

## Deployment

Очікується Web Auto Deploy після звичайного push feature-гілки. Backend/міграції не змінені. Railway-інструмент у сесії недоступний; фактичний deployment та staging QA не підтверджені локальними тестами. Production та staging-дані не змінювалися.
