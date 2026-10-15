# Звіт реалізації CarPot Warehouse MVP

Гілка: `feature/carpot-warehouse-mvp`. Весь модуль ізольовано в `warehouse/`. Існуючі tracked-файли CarPot не змінювалися. Нічого не змерджено і не задеплоєно; виконувалася тільки локальна розробка та перевірки.

## Реалізовано

- FastAPI REST API `/api/v1/`, OpenAPI/Swagger, SQLAlchemy, PostgreSQL, дві Alembic-міграції.
- Реєстрація, login/logout, Argon2id, хешовані серверні сесії, CSRF-захист, перевірка власника всіх business-ресурсів, обмеження спроб входу.
- Створення/редагування/пошук/фільтри/архів донорів, детальна картка, пов’язані запчастини та фінансові показники донора.
- Контрольований імпорт UTF-8 JSON із preview та підтвердженням, стабільні ключі та parent-child-ієрархія, однакові назви в різних гілках, атомарність та ідемпотентність.
- Стандартний чекліст із нульовими залишками, невідомими цінами й непідтвердженою наявністю; повторна генерація зберігає завершену роботу та архів.
- Картки запчастин з OEM/артикулом, категоріями, донором, станом, ціною/собівартістю, місцем, сумісністю, описом та внутрішніми примітками; індивідуальний облік із серійним номером; захищені фото при налаштованому сховищі.
- Надходження, списання, резерв/зняття резерву, абсолютне коригування і переміщення. Транзакції, блокування рядків PostgreSQL, CHECK-обмеження й атомарні масові операції.
- Незмінний аудит, повні before/after snapshots, фільтри дат/типу/автора/донора/деталі, soft archive та відновлення.
- Dashboard і аналітика на реальних даних. Оцінка запасів та потенційна маржа чітко відокремлені від фактичного доходу.
- React + TypeScript + Vite, українська мова, sidebar/topbar, усі вісім розділів, desktop-таблиці, мобільні картки, адаптивні форми, loading/error/empty states, пошук і фільтри.
- Незалежні Dockerfile/Compose, persistent volumes для development та окремий tmpfs PostgreSQL для тестів. Власні requirements + hash-locked dependency graph і npm lockfile.

## Схема бази

| Таблиця | Призначення |
|---|---|
| accounts | Акаунти, унікальна пошта, Argon2id hash |
| sessions | Хеші session/CSRF-токенів, акаунт, термін дії |
| vehicles | Дані донора, придбання, статус, архів; унікальний ID донора в акаунті |
| categories | Власник, джерело/ключ, тип, назва, parent_id, архів |
| parts | Картка, donor/category links, залишок/резерв, ціни, serial, checklist key, архів |
| operations | Автор, час, причина, тип, незмінні before/after, історичні посилання |
| photos | Метадані авторизованих фото; файли у незалежному storage volume |

Обмеження не дозволяють від’ємний залишок, резерв понад залишок, більше 1 одиниці для індивідуальної позиції, від’ємні ціни чи повторний checklist key для донора. Тригер PostgreSQL блокує UPDATE/DELETE аудиту. Ізоляція акаунтів реалізована на рівні API/сервісів, без PostgreSQL RLS.

## Перевірки

- **19 backend-тестів пройшли на PostgreSQL**, включно з реальними конкурентними резервуваннями останньої одиниці, перевіркою DB-тригера аудиту, фото, ізоляцією акаунтів та циклом міграцій downgrade/upgrade + Alembic schema check.
- **19 тестів пройшли в backend Docker-образі** на окремій `db_test`.
- **Два браузерні workflow** (desktop 1440×1000, iPhone 390×844) перевіряють реальні запити без mock API: реєстрацію, донора, імпорт, чекліст, надходження, резервування, аудит, меню та logout. Скриншоти: ігнорована `frontend/test-results/`.
- `npm run build` успішний: TypeScript і production Vite bundle, без помилок компіляції.
- `npm audit`: 0 відомих вразливостей після оновлення залежностей.
- `pip-audit` для hash-locked backend: відомих вразливостей не знайдено після оновлення залежностей.
- Ruff F-check і перевірка чистоти існуючих tracked-файлів пройшли.
- Повний локальний Compose запущено: backend і PostgreSQL healthy, frontend HTTP 200, авторизаційний API через Vite proxy очікувано повертає 401 без сесії, сторінка входу успішно відображається в Chromium.
- На окремому `warehouse_dev` застосовано міграції; підтверджено нуль користувачів, донорів, категорій, запчастин і операцій. `/health` та `/openapi.json` повертають 200; сторінка входу відображається без seeded accounts.
- Є одне deprecation-попередження тестового HTTP-клієнта Starlette (`httpx`); тести завершуються успішно, assertions не вимикалися.

Початкові Docker-збірки в cloud не могли вирішити DNS проксі й перевірити його CA. Це усунуто передачею актуального host mapping та системного довіреного CA через BuildKit secret. TLS, підписи/хеші пакетів не вимикалися. Helper: `scripts/build-cloud-images.py`; звичайному локальному Docker він не потрібен.

## Запуск і маршрути

Точні команди: [README.md](README.md). API-контракт: [API.md](API.md).

Звичайний локальний запуск після генерації власного `.env`:

```bash
cd warehouse
docker compose up --build -d
```

У цьому cloud образи підготовлюються helper-командами з README, потім `docker compose up --no-build -d`. Backend — локальний порт 8010, frontend — 5173. Swagger `/docs`, schema `/openapi.json`, health `/health`.

UI: `/`, `/vehicles`, `/catalog`, `/inventory`, `/operations`, `/analytics`, `/archive`, `/settings`.

## Межі MVP

- `AdvL_Nes_Tree_Raw.txt` відсутній. Для імпорту саме raw-таксономії потрібен оригінал та окреме підтвердження його формату/кодування. Зараз реалізовано безпечний JSON-контракт; повний OEM-каталог не вигадувався.
- Немає фактичних продажів, realized profit, платіжних/Telegram/CarPot-інтеграцій чи автоматичного розподілу вартості донора між деталями.
- Один власник на акаунт; командні ролі/запрошення, password recovery та account integration — майбутні розширення.
- Локальне фото-сховище; зовнішній object storage/CDN не інтегровано.
- Ліміт спроб входу працює в одному процесі. Розподілений limiter, очищення прострочених сесій і production-операційна інфраструктура не входять до MVP.
- Архівування батька не архівує дітей автоматично; журнал зберігає їхні зв’язки.
- Всі штучні записи існують лише в окремих тестових БД і тестових fixtures. Development не засівається.

## Нові файли

- `warehouse/.env.example`
- `warehouse/.gitignore`
- `warehouse/API.md`
- `warehouse/IMPLEMENTATION_REPORT.md`
- `warehouse/README.md`
- `warehouse/backend/.dockerignore`
- `warehouse/backend/Dockerfile`
- `warehouse/backend/alembic.ini`
- `warehouse/backend/alembic/env.py`
- `warehouse/backend/alembic/script.py.mako`
- `warehouse/backend/alembic/versions/eb8fddfe982f_initial_isolated_warehouse_schema.py`
- `warehouse/backend/alembic/versions/f482ab1376c0_immutable_audit.py`
- `warehouse/backend/app/__init__.py`
- `warehouse/backend/app/api/deps.py`
- `warehouse/backend/app/api/routes.py`
- `warehouse/backend/app/config.py`
- `warehouse/backend/app/db.py`
- `warehouse/backend/app/main.py`
- `warehouse/backend/app/models/__init__.py`
- `warehouse/backend/app/schemas/__init__.py`
- `warehouse/backend/app/services/analytics.py`
- `warehouse/backend/app/services/auth.py`
- `warehouse/backend/app/services/inventory.py`
- `warehouse/backend/requirements.lock`
- `warehouse/backend/requirements.txt`
- `warehouse/backend/tests/conftest.py`
- `warehouse/backend/tests/test_warehouse.py`
- `warehouse/docker-compose.yml`
- `warehouse/frontend/.dockerignore`
- `warehouse/frontend/Dockerfile`
- `warehouse/frontend/index.html`
- `warehouse/frontend/package-lock.json`
- `warehouse/frontend/package.json`
- `warehouse/frontend/src/App.tsx`
- `warehouse/frontend/src/api.ts`
- `warehouse/frontend/src/components.tsx`
- `warehouse/frontend/src/main.tsx`
- `warehouse/frontend/src/pages/Archive.tsx`
- `warehouse/frontend/src/pages/Audit.tsx`
- `warehouse/frontend/src/pages/Auth.tsx`
- `warehouse/frontend/src/pages/Catalog.tsx`
- `warehouse/frontend/src/pages/Dashboard.tsx`
- `warehouse/frontend/src/pages/Inventory.tsx`
- `warehouse/frontend/src/pages/Operations.tsx`
- `warehouse/frontend/src/pages/Settings.tsx`
- `warehouse/frontend/src/pages/Vehicles.tsx`
- `warehouse/frontend/src/shared.tsx`
- `warehouse/frontend/src/style.css`
- `warehouse/frontend/tests/browser-check.mjs`
- `warehouse/frontend/tests/workflow.mjs`
- `warehouse/frontend/tsconfig.json`
- `warehouse/frontend/vite.config.ts`
- `warehouse/scripts/build-cloud-images.py`

Згенеровані `.venv`, `node_modules`, `dist`, локальний `.env`, фото і тестові скриншоти ігноруються Git. Значення секретів не включені до комітованих файлів.
