# CarPot — Stage 7. Відкриття автомобілів у повній MySQL Oracle

**Статус:** код протестовано в CI; на Oracle VM та Railway ще **не застосовано**.
**Мета:** надати Catalogue staging доступ до повного довідника `manufacturers → models → passanger_cars/commercial_vehicles → attributes`, не торкаючись імпорту 50+ GB.

## Що працюватиме після розгортання

Приватний Oracle Adapter (всі маршрути, крім /health, вимагають `X-Oracle-Adapter-Key`):

- `GET /api/v1/oracle/vehicles/manufacturers?name=DAF&kind=commercial`
- `GET /api/v1/oracle/vehicles/models?manufacturer_id=<sourceID>&kind=commercial&after=0`
- `GET /api/v1/oracle/vehicles/modifications?model_id=<sourceID>&kind=commercial&after=0`
- `GET /api/v1/oracle/vehicles/attributes?car_id=<sourceID>&kind=commercial`

Для Volvo застосовувати `kind=passenger`. Ідентичні маршрути стають доступними через авторизований Catalogue gateway на `catalogue-staging` із `X-Catalogue-Key`.

Кожна відповідь — `vehicle_identity_only=true`, `fitment_verified=false`. Довідниковий ID **не є** доказом OEM-сумісності або factory VIN fitment. Після знаходження модифікації необхідно звірити двигун, тип палива, привід та інтервал випуску із VIN. Немає підтвердженого збігу — немає автоматичного OEM за іншою модифікацією.

## Гарантії безпеки

- Лише SELECT, сеанс MySQL READ ONLY; `max_execution_time=3000`.
- `manufacturers` — мала довідкова таблиця ~4380 рядків; `models` має індекс `manufacturerid`, `passanger_cars`/`commercial_vehicles` — індекс `modelid`, атрибути індексовані за car ID.
- Кожна відповідь до 50 рядків, з прапорцем truncation та курсором `after`; без масового SQL COUNT або DDL.
- Таблиці `article_li` і `article_links` НЕ використовуються. Oracle імпортер не зупиняти й не перезапускати.
- Лише staging, Tailscale HTTPS через внутрішній Relay. Немає публічного MySQL порту та нових секретів у GitHub.
- Фоновий OEM worker Warehouse не переводити на цей довідник автоматично, доки немає перевіреного `source_modification → PRD → article → OEM` графа.

## Обов'язкові передумови перед деплоєм

1. На Oracle перевірити існуючі дозволи окремого MySQL-користувача `carpot_catalogue_ro`. Історично SELECT було надано лише на три таблиці (`article_oe`, `article_cross`, `passanger_car_pds`). Нові маршрути вимагають **додаткового SELECT** на:
   `manufacturers`, `models`, `passanger_cars`, `commercial_vehicles`, `passanger_car_attributes`, `commercial_vehicle_attributes`.
   Немає дозволу → 503. Не змінювати DCL, не створювати користувачів та не друкувати паролі без окремої явної перевірки і погодження.
2. Оновити на Oracle VM **лише** `/opt/carpot/oracle-adapter/app.py` із GitHub гілки; зберегти резервну копію старого файлу, перевірити синтаксис і сервіс після перезапуску. Це не перезапускає MySQL.
3. Тільки після перевірки локального Adapter оновити `catalogue-api` у Railway `catalogue-staging`. Стандартні OEM маршрути повинні лишитись доступними.
4. Контрольні пошуки: Volvo manufacturer 120 → model 13084 (XC90 II) → car 107555 (T6 AWD); Volvo 120 → 37773 XC60 II (246), зокрема 126478..126482; DAF manufacturer ID і модель XF потрібно вперше прочитати з Oracle та зафіксувати, не вгадувати.
5. Tailscale Relay раніше неодноразово повертав `ConnectTimeout` при автоматичних запитах. Перед масовим підключенням VIN треба стабілізувати цей маршрут. Не збільшувати довільно тайм-аути.

## Пакети / контроль

- Catalogue branch: `feature/carpot-oracle-vehicle-discovery-20261122`.
- Oracle Adapter: `catalogue/oracle_adapter/app.py`.
- Railway Gateway: `catalogue/oracle_gateway.py`.
- Ізольовані тести: `catalogue/tests/test_oracle_vehicle_discovery_stage7.py`.
- CI: https://github.com/TsPa33/telegram-bot/actions/runs/45043425546 — **20 PASS** (за результатом GitHub Actions 22.11.2026).

## Чого не заявляємо

Немає фактичного живого SQL-виміру DAF XF чи VIN→модифікація для двох контрольних VIN у новому API. Немає підстав стверджувати, що `article_links` повністю імпортовано або досягнуто 90% OEM. Це етап безпечного discovery для майбутньої точнішої VIN-прив'язки.
