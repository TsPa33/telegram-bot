# CarPot №049 — VINState: контрольована інтеграція, без платних запитів

## Стан
- Користувач створив `WAREHOUSE_VINSTATE_API_KEY` у Railway `warehouse-staging/telegram-bot`.
- **Наявність ключа підтверджена через Railway; значення приховане.**
- Новий адаптер `app/services/vin_vinstate.py` відповідає офіційному endpoint `GET https://vinstate.com/api/v1/vin/{vin}` з `Authorization: Bearer ...`.
- Джерело **не включене** в автоматичну чергу `vin_lookup`, не включене у кнопку 50 грн, не викликається з UI.
- Новий адміністративний endpoint `GET /api/v1/vehicles/vin/vinstate/readiness` показує наявність ключа та стан тестового режиму (без значення ключа).
- `POST /api/v1/vehicles/vin/vinstate/preview` вимагає platform admin, активну сесію, CSRF, `vehicles.create`, `acknowledge_provider_quota=true`, **та** явне `WAREHOUSE_VINSTATE_TEST_ENABLED=true`. За замовчуванням повертає 503 і **не звертається** до VINState.
- Окремі тести з підробленим HTTP, без реального трафіку.

## Важлива інформація про ціни
VINState Free згідно з актуальними публічними цінами має **20**, а не 50 запитів, що повернули модель, на місяць. Після використання безкоштовної квоти API може списувати платні credits, якщо такі є. **Endpoint не гарантує режиму free-only.** Тому навіть діагностичний режим не вмикати без перевірки балансу на vinstate.com.

Джерела:
- https://vinstate.com/pricing
- https://vinstate.com/docs
- https://vinstate.com/static/terms-of-service

## Формат даних
Офіційний приклад:
`data: [{vin, decoded: {vehicle: {car: "2003 Honda Accord EX"}, wmi: {make: "Honda"}}}]`.
Отже **неправильно** вважати, що VINState завжди повертає окремі year, engine, body чи transmission. Адаптер безпечно витягує тільки явні поля з об'єктів vehicle/wmi. Значення `vehicle.car` залишено діагностичним текстом, але марка/модель/рік **не вгадуються** з нього. Поля з конкретного VIN можуть бути відсутніми.

## Приймання перед активацією
1. В акаунті VINState перевірити поточні залишки Free requests, кількість платних credits (краще 0), умови API.
2. Дозволити максимум два ручні тестові запити, які витратять лише включені запити за наявності квоти. **Не вводити API-ключ у чат.**
3. Окремо, після явної згоди на можливі витрати квоти, увімкнути `WAREHOUSE_VINSTATE_TEST_ENABLED=true` у `warehouse-staging` лише для короткого тесту.
4. Адміністратор перевіряє DAF `XLRTE47MS0E774889` та контрольні Volvo на справжніх відповідях; фіксує `vehicle`, `status`, `billing.funding_source`, `billing.charged_credits`.
5. Вимкнути `WAREHOUSE_VINSTATE_TEST_ENABLED`; оцінити якість/покриття до реальної оплати.

## Подальший етап
Підключення до 50 грн можливе лише після:
- перевіреного центрального Billing reserve/capture/release, idempotency і reconciliation;
- доказу нових корисних полів порівняно з NHTSA/FreeVINDecoder/CarAPI.dev;
- кешу з ліцензійними термінами й атомарним платіжним журналом;
- ліміту provider credits + контролю економіки 50 грн за запит.

Production, paid VIN API, LiqPay, billing environment, 50 грн реальні списання й локальну MySQL не змінювати.
