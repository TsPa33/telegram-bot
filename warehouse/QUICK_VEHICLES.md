# Швидке додавання автомобіля

## UX та джерела

Початкова форма: марка, модель, рік і необов'язковий двигун. Пошук марок/моделей
працює за частиною назви без урахування регістру, з listbox, ArrowUp/Down, Enter,
Escape та Tab. Невідомі назви додаються лише явним вибором «Використати …».
Зміна марки скидає модель, рік і двигун; зміна моделі — рік і двигун.
Наявні модифікації ніколи не вибираються автоматично.

`backend/app/data/vehicle_names.json` — невеликий вручну укладений довідник
поширених назв марок і сімейств моделей, незалежний від Plan.Parts. Він не містить
періодів виробництва, поколінь, сумісності, двигунів чи K-Type. Це неповні підказки,
не повний автокаталог і не дані, скопійовані з тестових JSON. При читанні backend
доповнює їх назвами з авто тільки поточного акаунта (включно з архівом).
Нові ручні назви зберігаються лише як дані автомобіля, не публікуються іншим акаунтам.

Без підтвердженого періоду модель має загальний список років від поточного до
1886, у спадному порядку. Це межі введення, не твердження про роки виробництва.
«Інший рік…» дозволяє уточнення в межах чинної серверної валідації 1886–2100.
Для моделей Plan.Parts використовуються відомі границі, null не підміняється
точною датою завершення. Конкретний двигун/K-Type залишається необов'язковим.

Відкриття форми виконує тільки безкоштовний внутрішній GET `/api/v1/vehicle-catalog`.
При помилці довідника ручне введення залишається доступним. Розділ «Точний підбір
Plan.Parts» активується явно; кожна кнопка завантаження — окремий запит. При
PLAN_PARTS_ENABLED=false локальне додавання працює. Живі запити, ключі й Railway
Variables для цієї зміни не потрібні.

Після збереження форма закривається, фільтри очищуються, список оновлюється,
повідомлення показує нове авто з кнопкою «Відкрити картку». У картці через
«Редагувати / додаткові дані» доступні VIN, ID, дата, вартість, покоління, паливо,
коробка, статус і примітки. Збереження основних полів не стирає ці дані.

## API та дані

POST `/api/v1/vehicles` приймає тільки manufacturer/model/year; engine, ktype та
другорядні поля необов'язкові. Невідома вартість — NULL, відомий нуль — 0.
Дата не підміняється поточною. Відсутній donor_id генерується backend:
`AUTO-<UUID hex>`, перевірка збігу з повторною генерацією, чинний DB
UNIQUE(account_id, donor_id) захищає від конкурентних дублікатів. Явний дубль — 409.
ID можна змінити в додаткових даних; порожній ID відхиляється.

PUT вимагає основну трійку та застосовує лише явно передані поля. При зміні
ідентифікаційних параметрів без нового явного K-Type старий K-Type очищується.
Додаткові зміни не очищують його. Старі чеклісти зберігаються як історія; перевірки,
переклади, залишки й резерви не змінюються. Аудит, авторизація, CSRF та account_id
залишаються чинними. Ніякого автоматичного import типів деталей чи stock receipt.

## Міграція — локально підготовлена, на Railway не запускалась

`b72f03d8e196_optional_acquisition_date.py`, після `a84d2c19e705`: лише
ALTER vehicles.acquisition_date DROP NOT NULL. Наявні дати, автомобілі, користувачі,
деталі та аудит зберігаються. Нові записи можуть мати NULL. Видалень, default,
вигаданих дат або backfill немає. Нова схема потрібна перед новим frontend.

Після окремого погодження rollout: перевірений backup Warehouse staging,
контрольований API release через чинний `app.staging` (advisory lock + upgrade head),
перевірка current/heads = b72f03d8e196, `alembic check`, HTTPS `/health`, потім web.
Не змінювати production. Не запускати міграції паралельно з entrypoint.

При збоях перевага forward fix. Downgrade до a84d2c19e705 відмовляється виконуватися,
якщо є NULL-дати; не вигадувати дати заради rollback. Старий образ може очікувати
іншу Alembic-ревізію та не пройти health. Зберегти backup, зупинити лише Warehouse
writes і погодити відновлення в окрему БД або сумісне виправлення. Жодного downgrade
чи restore в staging без погодження.

## Перевірки

Backend: виділена локальна PostgreSQL `*_test`,
`../.venv/bin/python -m pytest tests unit_tests -q` з WAREHOUSE_TEST_DATABASE_URL.
Покрито мінімальне створення, null/0, K-Type, конкурентні ID і колізії, account/CSRF,
міграцію зі старими даними, schema check, відмову небезпечного downgrade, незмінний
склад і чекліст після редагування. Провайдер підмінений, платних викликів немає.

Frontend: `npm run build`, `node tests/plan-parts.mjs`,
`node tests/plan-parts-checklist.mjs`. Production assets з mocked API, desktop та
390×844 iPhone viewport: локальний пошук, ручний fallback, скидання залежностей,
клавіатура, діапазони років, неоднозначні модифікації та K-Type. Це Chromium,
не справжній Safari/VoiceOver: їх потрібно перевірити вручну перед live rollout.
Ціль 10–20 секунд — продуктова вимога, а не підтверджений користувацький замір.

## Результат локального прогону та файли

137 backend-тестів успішні (одне deprecation-попередження залежності TestClient),
production-збірка успішна. Обидва offline production-browser сценарії та повний
складський workflow з реальною локальною PostgreSQL пройшли на desktop/iPhone
viewport. Plan.Parts у повному workflow вимкнено. Secret scan не знайшов секретів.
Локальний довідник: 24 марки та 93 сімейства моделей. Commit/push/Railway не виконані.

Змінені/нові файли (шляхи від warehouse/):

```text
PLAN_PARTS_CHECKLIST.md
PLAN_PARTS_STAGING.md
QUICK_VEHICLES.md
backend/alembic/versions/b72f03d8e196_optional_acquisition_date.py
backend/app/api/routes.py
backend/app/data/vehicle_names.json
backend/app/models/__init__.py
backend/app/schemas/__init__.py
backend/app/services/vehicle_catalog.py
backend/tests/test_plan_parts_migration.py
backend/tests/test_quick_vehicle.py
frontend/src/SearchSelect.tsx
frontend/src/VehicleForm.tsx
frontend/src/components.tsx
frontend/src/pages/Vehicles.tsx
frontend/src/style.css
frontend/tests/plan-parts-checklist.mjs
frontend/tests/plan-parts.mjs
frontend/tests/workflow.mjs
```
