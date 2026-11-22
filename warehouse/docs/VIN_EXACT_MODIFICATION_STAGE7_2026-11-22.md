# CarPot Warehouse — VIN → Source Modification, Stage 7 (2026-11-22)

## Проблема
Старе `SourceCache.directory_candidates` спочатку порівнювало марки/моделі/роки, а при розбіжності двигуна, типу палива або приводу все одно повертало першу `relaxed`-модифікацію. Це могло автоматично зіставити XC60 B5 Mild Hybrid 2022 із XC60 T5 AWD (`126480`) — модель/рік збігаються, силова установка **ні**. Також стара `automatic_catalogue_identity` зі статусом `auto_assumed` могла пережити повторні sweep-и та бути використана навіть із збереженим source snapshot.

## Виправлення
- Автоматичне присвоєння source ID лише за **єдиним найкращим кандидатом, підтвердженим технічними ознаками** (engine code, variant, fuel/drive/capacity). Точна назва покоління без двигуна недостатня.
- При однаковому найкращому рейтингу різних source ID немає автоприсвоєння. Жодного «першого зі списку» лише за роком.
- При суперечності VIN → джерельна модифікація немає підстав автоматично застосувати OEM. Додати донор і користуватися базовим планом CarPot можна.
- Історичні `auto_assumed` більше не використовуються як підстава для **нових** автоматичних OEM-записів, включно із раніше збереженими планами. Ручні `global_selection` та ручні OEM залишаються чинними.
- Нові автоматичні source IDs, отримані лише після унікального technical-match, мають `confirmation=catalogue_evidence` і **`vin_verified=false`**. Це кандидат із доказами, а не повний factory VIN-fitment.
- Історичні номери, вже записані в `Part`, а також облік продажів і складські кількості **не видаляємо автоматично**. Їх необхідно окремо перевірити у read-only аудиті.

## Контрольні VIN
- Volvo XC60 B5 AWD 2022 `YV4L12RK6N1970668`: старий XC60 T5 AWD не приймати автоматично.
- Volvo XC90 2016 `YV4A22PK2G1092943`: підтверджений еталон `source car_id=107555`, T6 AWD; за наявності точних характеристик розпізнається, але OEM покриття PRD окрема задача.
- DAF XF 2007 `XLRTE47MS0E774889`: якщо у поточному Catalogue directory немає DAF, повернути `None`, а не підставляти сторонній vehicle ID.

## Межі та передумови
- Oracle source discovery готується в окремій гілці Catalogue, а не «підключений» автоматично в Warehouse. Для DAF спершу треба підтвердити справжні source maker/model/car ID, мати read-only grants на `commercial_vehicles`, стабільний Tailscale Relay та після завершення імпорту — перевірений commercial PRD/article graph.
- Відсутня модифікація у `catalogue_volvo_snapshots` не доводить її відсутності у `td1q2018`.
- Staging only; жодні VIN/ключі не надсилати стороннім сервісам під час тестів; платний VIN API не викликати.
- Ніяких додаткових кнопок «Завантажити OEM» чи технічних сповіщень у UI.

## Перевірки
- `warehouse/backend/tests/test_unified_catalogue.py`
- `warehouse/backend/tests/test_vin_catalogue_identity_stage7.py`
- `warehouse/backend/tests/test_oracle_oem_auto.py`
- `warehouse/backend/tests/test_oem_diagnostics.py`
- GitHub workflow: `.github/workflows/carpot-warehouse-oracle-oem-stage6.yml`, ізольована PostgreSQL 16.

## Реліз
Deploy тільки в `warehouse-staging` після повного CI PASS; переглянути існуючі `auto_assumed` VIN записи і порівняти `plan_valid_oem`, `unmatched_source_prd` до і після. Не змінювати production.
