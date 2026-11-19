# CarPot — етап №056: довготривалі VIN-результати, тарифи та OEM

Дата: 2026-11-19.

## Перевірений стан перед змінами
- Три API-декодування Vincario (DAF XF, Volvo XC90, Volvo XC60) успішні, залишок Free Demo 17/20.
- Досі результати були лише в процесному Python словнику `_results`. **У PostgreSQL не збережено.** Після restart вони втрачаються.
- Модуль `auto_oem.py` існує й використовує free Catalogue API. Точне зіставлення каталожної модифікації та запчастини необхідне. За документацією `warehouse/docs/automatic-oem/README.md` доступний лише каталог Volvo 107555 у live directory; OEM-таблиця сама по собі не є перевіреним fitment graph.
- Тарифи Warehouse зараз задано кодом: `billing.PLANS` і `entitlements.PLANS` (Standard 1000 грн / 10 авто / 5 працівників; Premium 4500 грн / 50 авто / 10 працівників). Платний checkout вимкнений до підтвердження LiqPay.
- Запропонована користувачем цінова матриця (потрібне окреме затвердження): Starter 690 грн / 3 авто / 1 працівник; Standard 1490 грн / 10 авто / 5 працівників / 1000 внутрішніх credits; Premium 4490 грн / 50 авто / 10 працівників / 5000 credits; Business від 7990 грн / від 100 авто / від 20 працівників. **1000 внутрішніх credits не можна прирівнювати до 1000 платних API-запитів.**

## Виконано у PR
1. PostgreSQL table `vin_evidence_snapshots` із унікальністю provider+VIN+contract_version, нормалізованими полями, джерелом, статусом, часом, missing fields та відомими рахунками credits; без секретів і без повного провайдерського JSON.
2. `app/services/vin_evidence.py` — read/save/restore, зафіксовані значення для трьох контрольних VIN **лише з наданих користувачем API screenshots**, source=`user_supplied_api_result_screenshot`. Це не оригінальний Vincario JSON.
3. Адміністративні endpoints `GET /api/v1/vehicles/vin/vincario/trial/saved`, `POST /api/v1/vehicles/vin/vincario/trial/restore-controls`. Відновлення працює без мережі, повторне звернення ідемпотентне.
4. Admin UI у VIN «Технічні деталі»: «Зберегти 3 попередні результати VIN у базі (без API)» та «Переглянути збережені дані VIN».
5. Existing trial preview тепер читає PostgreSQL **до** Vincario та після нового успішного API тесту зберігає результат.
6. Тести підтверджують idempotent restoration, admin-only, no provider calls і кеш через HTTP.

## Важливі обмеження
- Автоматичне платне VIN enrichment у виробничому /vehicles/vin/decode **не активовано**. `WAREHOUSE_VINCARIO_ENABLED` залишити OFF.
- Кеш доступний лише platform-admin; міжорендний доступ у production потребує підтвердження ліцензії Vincario, tenant isolation, lifecycle і стійкого request ledger зі станами pending/settled/uncertain.
- Після розгортання не підміняти реальні VIN-поля авто без review; OEM fitment і точні коди двигунів цей snapshot не підтверджує.
- Три відновлені значення потрібно звірити з реальними API звітами, якщо вони збережені окремо; нових кредитів для цього не витрачати.
- Зміни staging-only; production, finance, тарифи і OEM таблиці незмінні.

## Наступні пакети
1. OEM read-only audit: простежити source MySQL -> Catalogue API -> modification/car_id -> product_id -> article/supplier -> OEM -> stock part; виміряти наявні матчі та пропуски по Volvo/DAF, не підставляючи неточні OEM.
2. Політика тарифів: versioned products, editable plan drafts, addons/features/API credit wallets, vendor unit-cost budgets, approval/publish/rollback і immutable active subscription snapshots. Не писати тарифи у static PLANS після підключення механізму.
3. Provider gateway: entitlement/quota, durable dedupe across workers, reuse license, fallback, retention, provider cost reports, audit.
4. UI: VIN card with provenance and conflict resolution; badges and technical debug hidden from ordinary users.

## Ідентифікатори
Фінальні SHA, GitHub PR, CI і Railway deployments зафіксувати тільки після фактичної перевірки.
