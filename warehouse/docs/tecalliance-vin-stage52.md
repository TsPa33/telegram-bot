# CarPot — етап 052: TecAlliance Vehicle Identification (VIN)

## Перевірений офіційний контракт

**Джерело:** глобальний TecAlliance Vehicle Identification Service, **не** China OneDB:
- https://vehicle-identification.tecalliance.services/documentation/introduction
- https://vehicle-identification.tecalliance.services/documentation/news
- https://vehicle-identification.tecalliance.services/documentation/vin/v1/attributes
- https://vehicle-identification.tecalliance.services/documentation/vin/v1/swagger

Новий VIN endpoint: `/api/v1/vin/:country/:vin`. VIN має 17 символів. У відповіді може бути **кілька** `vehicles` із `ktype` для легкових і `ntype` для комерційних транспортних засобів. Для уточнення доступні make, model, dateFirstReg, body, doors, fuel, gearboxType, gearboxCode, cc, kw, engineCode (точну передачу параметрів перевірити за чинним OpenAPI й договором).

TecAlliance вказує, що коли VIN не прив'язано до TecDoc KType/NType, повертається **404**, а не гарантований рік/двигун. `salesStartDate` і `salesEndDate` є періодом продажів модифікації, **не** роком конкретного автомобіля.

Документація v1 містить `vehicleInformation`, `engine`, `gearbox` з характеристиками. Це каталожна відповідність, не підтвердження фактичної заводської комплектації.

## Реалізація цього пакета

- `app/services/vin_tecalliance.py` — ізольований **offline parser** із контрактом KType/NType, кандидатами, явними технічними характеристиками, без вигадування року.
- `app/api/vin_tecalliance.py` — `GET /api/v1/vehicles/vin/tecalliance/readiness`, тільки platform admin і чинні права; не робить HTTP до TecAlliance.
- Маршрут внесено до allowlist і permissions; тести перевіряють відсутність платних запитів, обробку кількох результатів і неоднозначної КПП.
- **Не додано:** живий HTTP-клієнт, платний виклик, мерчант-рахунок, міграцію БД, автоматичне призначення KType/NType, інтеграцію в кнопку 50 грн.
- `WAREHOUSE_TECALLIANCE_API_KEY`, `WAREHOUSE_TECALLIANCE_COUNTRY` можуть використовуватися лише для відображення готовності. Ключа в Railway станом на 2026-11-19 немає. Не додавати випадковий токен OneDB China — це інший API.

## Що слід погодити з TecAlliance до активації

1. **Commercial access:** тестовий API token для **Global Vehicle Identification VIN v1**, а не China OneDB.
2. **Auth:** точна схема OAuth/API-key, заголовки, регіональний base URL, дозвіл тестового оточення, схема retry/error.
3. **Country:** які значення `:country` підтримуються для VIN українських, німецьких, нідерландських та інших зареєстрованих авто; чи є глобальна опція.
4. **Coverage:** 10 контрольних VIN (DAF XLRTE47MS0E774889, Volvo XC90 2016, XC60 2022, інші легкові та вантажівки) із кількістю результатів, KType/NType та наявністю engine/gearbox/body.
5. **Pricing:** мінімальний платіж, ціна lookup, ціна 404/кількох кандидатів, тарифні пакети, поточна квота, скільки запитів дозволено на staging, чи можливий top-up по одному запиту і cap бюджету.
6. **Licensing:** платний мультиорендний складський SaaS CarPot в Україні; право зберігати нормалізовані характеристики й KType/NType, повторно показувати користувачам, строк кешу й використання даних у fitment/OEM.
7. **Data model:** чи потрібна окрема TecDoc reference-data ліцензія; контракт VIN + TecDoc parts lookup, і чи входить його вартість до тарифу.
8. **Guarantees:** coverage не 100%; обробляти 404, конфлікти, неоднозначні модифікації як окремий бізнес-сценарій.

## Пропонована економіка кнопки 50 грн

Безкоштовний decode → перевірка вже оплаченої дозволеної копії → quote 50 грн → центральний Billing reserve → **один** платний виклик із фіксованим provider request key → збереження кандидата / вибір модифікації → capture тільки коли є нові придатні підтверджені поля; в іншому разі release за бізнес-правилами. Дубль не повинен створювати друге платне звернення. Поки механізм реально **не підключений**; confirm відповідає 503.

## Розгортання

Дозволено staging-only після PASS CI. Endpoint readiness не робить жодних платних дій. Production залишається без змін.
