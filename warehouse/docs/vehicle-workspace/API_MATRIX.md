# Матриця Plan.Parts — стан перевірки 2026-11-06

Нової офіційної документації з цього середовища отримати не вдалося (CONNECT
403). «Підтверджений контракт» нижче означає наявні експорти/fixtures і чинний
код, **не** партнерські права, реальний тариф або новий live-тест.
Provider base: `https://cdn.plan.parts/api`; HTTP GET з server-side Bearer.
Warehouse викликає lookup через POST з сесією/CSRF.

| Provider path | Підтверджені поля | Токени | Контракт | Збереження / застосування |
|---|---|---|---|---|
| `/v1/aftermarket/catalog/brands` | brand, mfa_id | Не підтверджено | array або success/data/results | response raw+normalized; марка |
| `/v1/aftermarket/catalog/models?mfa_id=…` | ms_id, name, production years; optional echoed brand | Не підтверджено | name field конфігурований; strict selector | response; модель |
| `/v1/aftermarket/catalog/modifications?ms_id=…` | ktype, modification, displacement_cc, power_kw/ps, production years | Не підтверджено | typed modification, optional unknown fields raw | response; явний вибір K-Type |
| `/v1/aftermarket/ktype?brand=…&model=…&year=…` | ktype, modification, optional brand/years/power | Не підтверджено | наявний mock contract; не новий live доказ | response; кандидат модифікації, не VIN decoder |
| `/v1/aftermarket/catalog/categories?ktype=…` | pt_id, name, article_count | Не підтверджено | source types; count не stock quantity | response + existing VehicleChecklistItem |
| `/v1/aftermarket/catalog/articles?ktype=…&pt_id=…` | art_id, article_nr, brand, optional/null part_name, optional img_url | Не підтверджено | optional total/limit/selectors; partial tracked | response + receipt snapshot; explicit Part assignment |
| OEM/cross endpoint | **Не підтверджено** | Невідомо | Не вигадуємо endpoint | API кнопка disabled; ручний OEM окремо |
| Аналоги, technical attributes, detail/fitment endpoint | **Не підтверджено** | Невідомо | Невідомі public fields з отриманої відповіді залишаються в raw | Немає нових зовнішніх викликів/автоматичних fitment тверджень |

В усіх випадках body зберігається до domain parsing, з sanitized SHA-256,
account/actor/context/schema/timestamps. Actual charge nullable: не підміняється
configured maximum. Невідомий тариф блокує новий cold request. Source brands
не трактуються як OEM автовиробника, а каталог — як фактично встановлена деталь.

Для активації: офіційний endpoint/schema + permission на retention/reuse +
тариф + reviewed PII fields + read-only перевірка staging isolation. Тоді
окремий контрольований сценарій з дозволу власника. Тут не виконувалося.
