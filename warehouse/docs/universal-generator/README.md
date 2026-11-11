# Єдиний генератор каталогів — 2026-11-11

Branch: `feature/assembly-component-inventory`, base `8269cb0c48a567a091ffc0825d70793136b999d6`.

## Робочий процес

Додати будь-яке підтримуване авто через VIN/вручну → «Розбір і запчастини» → **«Сформувати каталог»** → переглянути джерела, кількість типів/позицій/категорій та застосовність → **«Зберегти перелік»** → підтвердити фактичну наявність у чинному дереві → за потреби виконати чинне явне надходження на склад.

Генерація створює тільки потенційний план, не Part/залишки/резерви/продажі. Логічна початкова кількість позиції не є доведеною кількістю установчих місць. OEM/артикули не вигадуються. Поточна наявність та джерельна застосовність — різні статуси.

## Одна архітектура

- Розширено чинний `PlanPreview` опцією `universal`, за замовчуванням false для сумісності старих сценаріїв. Використано ті самі `/dismantling-v3/preview` та `/save`, token, etag, actor/workspace guard, advisory lock і DismantlingRequest replay. Нових endpoint/черг/моделей/міграцій немає.
- `universal_generator.py` — лише адаптери джерел до існуючого preview, не другий persistence engine. Усі записи залишаються DismantlingItem, Vehicle.dismantling_v3 та чинною історією Operation. AssemblyMembership і Part не змінюються.
- VIN 2.0 attributes використовуються як reported facts: engine_code тільки з окремого поля/явного атрибута, а не regex з EngineModel; drive/body та явно вказана електрифікація, fuel/transmission нормалізовані. Бензин сам по собі не доводить відсутності гібриду. Відсутність значення не означає несумісність.
- Підтверджений інженерний профіль не перезаписується VIN-даними. Суперечність нових VIN/Vehicle-значень із перевіреними powertrain/drive/engine_code/body facts дає unknown, не хибне виключення.
- Зміни VIN attributes, engine code, drive та інших identity-полів входять у стан preview. Зміна після preview блокує save; після збереження позначає план застарілим і прибирає довіру до старої застосовності, не видаляючи фізичні рішення.

## Джерела і пріоритет

1. Точний прив’язаний **manufacturer/model/modification/source snapshot**, спільний Catalogue API `global_source=True` для будь-якої марки. Перевіряються IDs, checksum/contract, pinned snapshot і вихідні характеристики; жодного зіставлення тільки за назвами. Збережений валідний compact source plan читається локально; інакше — лише read-only запит до чинного Catalogue API. `partial` дозволений. Зміна snapshot/модифікації не змішується автоматично.
2. Опубліковані CanonicalType/CanonicalPlacement, включно з підготовленим PRD provenance `universal_publication`, `universal_sources`, `declared_placements`, `fitment_rules`. Лише явно оголошені позиції; ринкова кількість пропозицій не породжує позицій. Тест додає один owner-publication fixture і доводить підхоплення без нової логіки під модель. **Повні 26 938 PRD не публікувались**.
3. За відсутності точного зв’язку — вже наявний curated `canonical_universal_v2c.json` + існуючі CarPot definitions. Не додано synthetic 552, випадкових деталей або списків Volvo. Загальні функції показуються як possible/unknown, не як заводський BOM. Довідник орієнтований на легкові авто; непідтверджені спеціальні комплектації/інші класи потребують джерельних даних.
4. Наявний model-scoped каталог workspace додається через чинний scope-resolver без порушення ізоляції.

Якщо точний source-каталог частковий, його не роздуваємо одночасним додаванням непов’язаних загальних типів, щоб не створити концептуальні дублікати. Непогоджені типи/витратні матеріали не видаються за підтверджені фізичні деталі; прогалина відображається явно. Розширення каталогу — дані/owner publication, не новий generator для марки.

## Статуси і безпека повторення

- «Підтверджено джерелом»: точна модифікаційна асоціація або явний reviewed source rule. Це не фізична наявність і не гарантований VIN-fitment; за конфлікту конфігурації лишається unknown.
- «Можливо»: доступна загальна конструктивна функція без доказу встановлення.
- «Потребує уточнення»: невідомі/неперевірені/конфліктні характеристики або неоднозначна ідентичність.
- «Несумісно»: тільки перевірені характеристики + явне обмеження. Unknown не вилучає запис; несумісні кандидати також видимі, не видаляють історію.

Корпоративні SECTIONS/SUBCATEGORIES використано для display-проєкції. Непогоджені категорії/підкатегорії позначені й включені в gaps, не вигадані. Нові типи/категорії в глобальну БД не публікуються.

Stable canonical/source identities запобігають повторному додаванню. Один exact source ID може без зміни старої назви/кількості зв’язати незв’язаний legacy item; уже прив’язана інша identity переходить на review. Складську identity не можна переприв’язати до іншого типу. Неоднозначні групи відкладаються чинним partial_plan; pending пропозиції залишаються видимими, не видаються за складські позиції. Історичні імена, ручні presence/note, included/status/quantity, Part, reserved_quantity, продажні ціни/валюта, AssemblyMembership та минулі Operation не перезаписуються.

## Мінімальні перевірки

Контрольні записи — **локальні синтетичні конфігурації**, не фактичні комплектації реальних Volvo або proof live-даних.

| Контроль | Доступні типи | Потенційні позиції | Визначені категорії | Possible / unknown до доказів |
|---|---:|---:|---:|---|
| Volvo XC60 2022 | 216 | 227 | 12 | 9 / 218 |
| Volvo XC90 2016 | 216 | 227 | 12 | 9 / 218 |
| Renault ZOE 2020, явно reported BEV | 216 | 227 | 12 | 9 / 218 |

Однакова кількість навмисна: без точного модифікаційного джерела й verified facts не можна вигадати відсутність деталей. Це доступне fallback-покриття, **не модельний BOM**, не 500+ доведених фізичних деталей. Окремий контроль verified BEV з owner-published combustion-only PRD дає incompatible; за суперечливої зміни VIN-атрибутів стає unknown. Інший synthetic manufacturer/modification partial source дає source-confirmed зв’язок без автоматичного підтвердження фізичної наявності.

Результат: **9 backend tests PASS; TypeScript/Vite build PASS; browser QA PASS**. Логи цільових backend-тестів, TypeScript/Vite build та локального browser QA — в `evidence/`. Перевірено три конфігурації, regeneration/replay, збереження двох ручних підтверджень, Part qty/reserve/price/currency, membership/history, exact source reuse, source/unknown separation, stale token і workspace isolation. Старий non-universal preview/save також перевірено. Повний regression не запускався.

Браузер 1440/390: preview → save 227 потенційних позицій → reload → нових при повторі 0; Part=0; жодних платних/decoder запитів або JS errors. GET історичного plan-parts-checklist допускається: він читає PostgreSQL, не викликає supplier API. [Desktop](screenshots/preview-1440.png), [Mobile](screenshots/saved-390.png).

## Staging

Push дозволений у чинну staging source branch `feature/assembly-component-inventory`. Авторизований Railway connector/CLI/credentials у Codex недоступні; ручного deployment або Variables changes не виконано. Auto Deploy після push очікується, але active API/Web SHA та живий сценарій залишаються UNVERIFIED до перевірки через підключений Railway.

Застосунок, підтверджений власником: https://confident-sparkle-warehouse-staging.up.railway.app . Production, worker settings, платні API, catalogue publish, реальні складські дані не змінювалися.
