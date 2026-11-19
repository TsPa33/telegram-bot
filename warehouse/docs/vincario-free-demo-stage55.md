# CarPot Checkpoint №055 — Vincario Free Demo: 3 контрольні VIN

Дата: 2026-11-19

## Підтвердження квоти
- Користувач надав повідомлення Vincario Support, що API account fully configured і доступні **20 безкоштовних VIN Decode** + по 5 Stolen Check та Market Value й 5 OCR.
- CarPot staging після виправлення balance parser №054 повернув фактичне **VIN Decode: 20**, Stolen Check: 5, Market Value: 5, OEM VIN Lookup: 0, OEM Service History: 0.
- Ключі `WAREHOUSE_VINCARIO_API_KEY`, `WAREHOUSE_VINCARIO_SECRET_KEY` уже є в Railway `warehouse-staging / telegram-bot`. Значення ніколи не викладати.
- `WAREHOUSE_VINCARIO_ENABLED` **не вмикати**; основна VIN-послідовність CarPot залишається безкоштовною.

## Контрольні VIN і перевірені вебзвіти
1. DAF XF 2007 — `XLRTE47MS0E774889`: tractor, diesel, 12,902 cc, RWD; transmission, exact engine code відсутні.
2. Volvo XC90 2016 — `YV4A22PK2G1092943`: SUV/MPV, gasoline, 1,969 cc, automatic, 4x4; exact engine/gearbox code відсутні.
3. Volvo XC60 2022 — `YV4L12RK6N1970668`: SUV/MPV, gasoline+electric, 2,000 cc as shown, AWD; transmission, exact engine code відсутні. Carvago advertisement power 145 kW **not** a value for this VIN.

## Реалізація №055
- `app/services/vin_vincario_trial.py`: окремий ручний staging-only client `decode/{VIN}.json` зі SHA1(`VIN|decode|key|secret`)[:10]; рівно три allowlisted VIN.
- Для кожного тесту: явне підтвердження адміністратора, перевірка `API Decode` через існуючий balance, тільки при 18–20 перед запитом; після 17 запуск блокується. Таким чином тестовий пакет не повинен витратити більше трьох із початкових 20 кредитів.
- Стисле нормалізоване представлення характеристик, статус, відсутні важливі поля, баланс до/після.
- У пам’яті процесу кеш на повторний ручний запит за тим самим VIN. Це **не** транзакційний довготривалий кеш: після restart або кількох replica захист від дубля забезпечується лише глобальним обмеженням балансу; продуктивному шлюзу потрібен PostgreSQL request ledger.
- `app/api/vin_vincario_trial.py`: readiness GET та preview POST, Auth/CSRF, platform admin; route allowlist та vehicles.create через існуючий /vehicles/vin/vincario/ prefix.
- Кнопка ручного тесту у «Технічні деталі» під існуючим балансом Vincario. Без автоматичного збереження авто, інтеграції Warehouse VIN lookup або 50 грн Billing.
- `Make Logo` тільки наявність поля; URL/файл не передається у UI та не зберігається до перевірки ліцензійних прав.
- Ніяких market value, stolen, OEM, OCR запитів.
- Офлайн-тести покривають DAF, числовий рік, авторизацію, три VIN, баланс, повторне використання.

## Бізнес-висновок
Якщо JSON відрізняється від вебзвіту, платне API автоматично не запускати; записати невідповідність по кожному VIN. Навіть якщо API має 20 credit, це не означає 100% точності.
- Реальний ліміт Free Demo підтверджено підтримкою користувача.
- Платна передплата €49, CarPot wallet reserve/capture/release, production: не змінені.

## Наступна дія
1. GitHub CI PASS, лише staging deployment backend+frontend.
2. Після доступності UI користувач окремо запускає DAF, XC90, XC60 (по одному, із підтвердженням).
3. Зафіксувати баланс 20 → 19 → 18 → 17 та нормалізовані поля.
4. Порівняти API JSON з перевіреними звітами й прийняти рішення щодо комерційного плану.

## Фактичні ідентифікатори
Доповнити після CI: commit SHA, PR, workflow, deployment IDs, status.
