# CarPot VIN — контрольна точка №053: Vincario API баланс без оплати

Дата: 2026-11-19.

## Передумови
- Vincario 3.2: `GET /3.2/{API_KEY}/{CONTROL_SUM}/balance.json`, SHA-1 перші 10 символів від `balance|API_KEY|SECRET_KEY`, дані офіційної документації від користувача.
- `WAREHOUSE_VINCARIO_API_KEY` і `WAREHOUSE_VINCARIO_SECRET_KEY` знайдено за **назвами** в Railway `warehouse-staging/telegram-bot`. Жодне секретне значення не виводилось.
- Колишній VIN адаптер `vin_europe.py` використовує `/decode/` тільки якщо `WAREHOUSE_VINCARIO_ENABLED=true`. Цей прапорець не змінено.
- Значення API Decode на прикладі JSON Swagger **не є балансом акаунта**; невідомо, чи тестова квота активна.

## Реалізація
- `app/services/vin_vincario_balance.py`: обмежений, **ручний** (за запитом адміністратора) виклик тільки endpoint балансу, сувора обробка 5 категорій балансу, без виведення ключів чи повного JSON, staging-only.
- `app/api/vin_vincario_balance.py`: readiness GET (без зовнішніх запитів) і balance POST (лише platform admin, сесія, CSRF, vehicles.create).
- Додано до `app/main.py`, явного route registry, permissions.
- В адмінському розділі «Технічні деталі» кнопка «Vincario: перевірити API-баланс»; натискання робить **один** запит балансу, не робить VIN-декодування.
- Тести `test_vincario_balance.py`: офіційний checksum, безпечна відповідь, staging gate, лише endpoint балансу, захист роллю.
- CI `.github/workflows/warehouse-assembly-split-pr5.yml` розширений на тести балансу.

## Заборони
- Жодних автоматичних викликів Vincario.
- `WAREHOUSE_VINCARIO_ENABLED` не активувати.
- Жодного резерву/списання 50 грн; жодного API /decode під час етапу №053.
- Не вважати `API Decode > 0` доказом, що квота безоплатна. Уточнити тип квоти/умови Free Demo до розшифровки VIN.
- Не переписувати production або main; staging-only.

## Наступний етап
- Користувач натискає «Vincario: перевірити API-баланс» у Warehouse, надає **лише числа та статус** (без ключів).
- Уточнити, що залишок відноситься до Free Demo, а не до платного тарифу.
- Після підтвердження розробити окремий адміністративний тест трьох VIN з quota cap=3, кешем і зіставленням із вебзвітами.
