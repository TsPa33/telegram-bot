# Відновлення початкового сценарію розбору

База: 43206d63355d2cea19079adca2c8c4be9bee0c34.

Причина: VirtualDismantling обирав professional за самим K-Type, не перевіряючи
наявність каталогу. Цей режим приховував базову кнопку навіть на новому авто.

Виправлення:
- Нове авто без збереженого плану/каталогу: один блок «Розібрати на запчастини».
  Після натискання — базовий CarPot або Plan.Parts. Порожні категорії не показуються.
- Джерело при відкритті визначається фактично збереженими server records; UI-вибір
  джерела запам'ятовується окремо для користувача/workspace/донора. Дані не
  залежать від browser cache. Після зміни K-Type робочий сценарій не скидається.
- Базовий preview/створення/оновлення повторно використовують чинні API та
  idempotency. Віртуальна позиція на автомобілі — не фізичне надходження.
  Ledger, quantity assumptions та операції не переписувалися.
- Plan.Parts спочатку виконує лише cache-only recovery. Відновлена відповідь
  зберігається в checklist для цього авто/K-Type, без Part/receipt.
  При відсутності отриманих даних новий запит потребує чинного тарифу/підтвердження.
- Без K-Type показаний вибір модифікації; вже отримані відповідні модифікації
  читаються з PostgreSQL без звернення до постачальника. Новий пошук — тільки
  з підтвердженням вартості. Ручний ID залишається в «Технічні деталі».
- Технічний K-Type/PostgreSQL приховані в згорнутому розділі; основні статуси:
  «Список збережено», «Дані отримані раніше», «Потрібно вибрати модифікацію».
- Категоризатор, дизайн категорій/таблиці, фільтри, bulk selection, права,
  призначення артикулів/OEM і захист paid requests не змінені.

Цільові перевірки:
- 5 backend tests PASS: free category restoration/persistence/replay без stock;
  scoped saved modifications/read-only; existing category recovery; base GET
  no-writes і explicit activation. Повного backend regression не запускали.
- Frontend build PASS.
- Реальна production frontend build + local PostgreSQL + MockTransport browser:
  A — ALFA ROMEO 147 2009 із K-Type, але без плану: початкова кнопка, вибір,
  preview, підтвердження, 227 віртуальних позицій; фізичних receipts немає.
  B — reload: ті самі item IDs, без дублікатів.
  C — попередньо збережений synthetic Plan.Parts: 96 типів, reload без paid lookups.
  Додатково авто без K-Type: підказка вибору, без порожніх категорій і видимої
  технічної інформації. Desktop 1440 / mobile 390, JS errors відсутні.
- Це синтетичні локальні донори, не фактичний staging донор №24/Volvo B.
  Реальних токенів витрачено 0; реальні складські записи не змінювалися.

Запуск: guarded tests/vehicle_workspace_server.py і seed_vehicle_workspace.py
із WAREHOUSE_E2E=1 та окремою loopback:55440 *_test PostgreSQL; production build
preview на 5223 з API proxy на 8022. Потім:
WAREHOUSE_E2E=1 node tests/dismantling-start-browser.mjs

Змінені production-файли: frontend/src/VirtualDismantling.tsx,
frontend/src/PlanPartsDonorAnalysis.tsx, backend/app/api/plan_parts.py.
Міграцій і змін Railway Variables/configuration немає. Head bd18a9f37c20 незмінна.

Railway App/CLI відсутні. Вже встановлений CONNECT 403 не перевіряли повторно.
Поточна ізоляція, фактичний deployment SHA і доступність staging — UNVERIFIED.
Публікація залежить від невиконаної умови підтвердження staging isolation з
попереднього релізного запиту. Автоматичний deployment не оголошується успішним.
