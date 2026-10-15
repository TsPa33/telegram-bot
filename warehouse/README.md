# CarPot Warehouse

Самостійний MVP обліку автомобільного складу: донори, ієрархія категорій, стандартні чеклісти, запчастини, залишки, резерви й незмінний аудит. Український адаптивний інтерфейс без демонстраційних даних.

Усі залежності, міграції, конфігурація і код містяться в `warehouse/`. Існуючий CarPot не імпортується, його `DATABASE_URL`, Telegram-токени, стартові файли та production-база не використовуються. Деплой не виконувався.

## Локальний запуск через Docker Compose

Потрібні Docker Engine і Compose v2. З кореня репозиторію:

```bash
cd warehouse
python3 - <<'PY'
from pathlib import Path
import secrets
p = Path('.env')
if p.exists():
    raise SystemExit('.env already exists; preserve it and configure it manually')
p.write_text('WAREHOUSE_POSTGRES_PASSWORD=' + secrets.token_hex(24) + '\nWAREHOUSE_COOKIE_SECURE=false\n')
p.chmod(0o600)
PY
docker compose up --build -d
```

Це створює окремий `warehouse_dev`, порожні таблиці та незалежні volumes `warehouse_db` і `warehouse_photos`. Міграції застосовуються перед стартом API. Жодних початкових користувачів, донорів, категорій чи запчастин немає. Створіть власний акаунт через реєстрацію.

- Frontend: порт `5173` локального комп’ютера.
- Backend: порт `8010`; Swagger `/docs`, OpenAPI `/openapi.json`.
- PostgreSQL: локальний порт `55433` (окремий від CarPot).
- Порти прив’язано тільки до `127.0.0.1`. Vite проксіює `/api` на backend; CORS не потрібен.

```bash
docker compose ps
docker compose logs backend
curl --fail http://127.0.0.1:8010/health
docker compose down
```

`down` зберігає дані. Не додавайте `-v`, якщо їх потрібно зберегти. Пароль у `.env` має бути випадковим URL-безпечним значенням; приклад генерації вище використовує hex. Зміна пароля в `.env` не змінює пароль уже створеної бази.

Compose призначений для локальної розробки. Для HTTP у ньому явно вимкнено secure-прапорець cookie; стандарт backend — `WAREHOUSE_COOKIE_SECURE=true`. Зовнішня публікація, HTTPS, резервне копіювання, обмеження доступу й production-інфраструктура не входять до цього завдання.

## Запуск без контейнерів для коду

Потрібні Python 3.11, Node 22+ та **окрема порожня PostgreSQL-база Warehouse**. Можна запустити тільки її через `docker compose up -d db` після створення `.env`.

```bash
cd warehouse
python3.11 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r backend/requirements.lock
```

У shell налаштуйте `WAREHOUSE_DATABASE_URL` через ваш локальний менеджер конфігурації. Формат: `postgresql+psycopg://warehouse:<URL-encoded-password>@127.0.0.1:55433/warehouse_dev`. Не копіюйте туди CarPot `DATABASE_URL`. Backend відхиляє інші драйвери та назви баз, які не починаються з `warehouse` або `carpot_warehouse`.

```bash
export WAREHOUSE_COOKIE_SECURE=false
# Необов’язкове локальне сховище фото:
export WAREHOUSE_PHOTO_DIR="$(pwd)/uploads"
cd backend
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

В іншому терміналі:

```bash
cd warehouse/frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

Усі задачі вже ізольовані; використовуйте поточний checkout. Новий Git worktree для цього модуля не потрібен.

## Перший робочий сценарій

1. Зареєструйте акаунт (пароль: 12–128 символів).
2. Додайте автомобіль із власним ID донора.
3. Імпортуйте свою таксономію або додайте запчастини вручну.
4. У картці донора натисніть **«Сформувати список запчастин»**.
5. Перевірте деталі: наявна / відсутня / пошкоджена / не перевірено.
6. Для фізично отриманих деталей проведіть **надходження** з кількістю і причиною. Сам факт підтвердження наявності не оприбутковує одиниці.
7. Виконуйте резерви, списання та переміщення через складські операції; переглядайте аудит.

## Імпорт каталогу

`AdvL_Nes_Tree_Raw.txt` у workspace не знайдено. Повний автомобільний каталог не вигадувався. Щоб написати адаптер саме цього raw-файлу, потрібен оригінал для перевірки кодування та ієрархії. Довільний raw-текст не інтерпретується навмання.

Доступний контрольований формат **UTF-8 JSON** (BOM дозволено), до 4 МБ і 10 000 вузлів, глибина до 32. Структура:

```text
{
  "source": "<стабільна-назва-джерела>",
  "nodes": [
    {"key": "<ключ-категорії>", "name": "<ваша-назва>", "kind": "category", "parent_key": null},
    {"key": "<ключ-підкатегорії>", "name": "<ваша-назва>", "kind": "subcategory", "parent_key": "<ключ-категорії>"},
    {"key": "<ключ-деталі>", "name": "<ваша-назва>", "kind": "part", "parent_key": "<ключ-підкатегорії>"}
  ]
}
```

Це опис формату, не готовий каталог для імпорту. Всі батьки мають бути в тому самому документі. Вузол `part` не може мати дітей. Цикли, повтори ключів і відсутні батьки відхиляються. Однакові назви в різних гілках дозволені. Унікальність визначає `(account_id, source, external_key)`, а не назва.

Інтерфейс спочатку перевіряє файл через dry-run, потім потребує явного підтвердження імпорту. Повторний імпорт не дублює записи, не знімає архівування і не переписує ієрархію існуючих ключів; конфлікт повертає `409` і відкочує весь імпорт. Для зміненої таксономії використайте нове джерело/ключі. Автоматичного імпорту немає.

Чекліст генерується тільки з активних вузлів `part`, у яких весь ланцюжок батьків активний. Нові позиції: кількість 0, резерв 0, «не перевірено», ціна/собівартість `null`, OEM та сумісність порожні. Це **можливі деталі, а не точний OEM-каталог**. Повторна генерація не змінює існуючих позицій, включно з архівними.

## Облік та безпека

- Argon2id для паролів; випадкові сесії на 7 днів. У БД зберігаються тільки хеші session/CSRF-токенів. Cookie сесії: HttpOnly, SameSite=Strict.
- Усі business API перевіряють акаунт, усі зміни додатково потребують `X-CSRF-Token`. У браузері токен береться з `warehouse_csrf` cookie.
- Авторизація не залежить від прихованих кнопок: сторонні ID повертають `404`. Ізоляція забезпечується сервісними перевірками власника та SQL-фільтрами; PostgreSQL RLS у цьому MVP не застосовується.
- Кількість не можна змінити через редагування картки. `SELECT FOR UPDATE`, транзакції та CHECK-обмеження захищають `quantity >= reserved >= 0`. Масові операції атомарні й блокують рядки в стабільному порядку.
- Коригування задає **абсолютний** новий залишок. Списання не може витрачати резерв; спершу зніміть його. Для індивідуального обліку потрібен унікальний серійний номер, кількість не перевищує 1.
- Історія містить автора, timestamp, причину, повний стан до/після та посилання на донора/запчастину. PostgreSQL-тригер відхиляє UPDATE і DELETE журналу. Адміністратор БД із правами зміни схеми, звичайно, не є недовіреним користувачем застосунку.
- Архівування не видаляє записи й не змінює дочірні записи автоматично. Позицію з резервом архівувати не можна. Активні метрики виключають архівні позиції; історія їх зберігає.
- Надходження/коригування оновлюють статус наявності. Стан і перевірка наявності — окремі характеристики, не заміна кількісного обліку.
- Фото доступні тільки якщо `WAREHOUSE_PHOTO_DIR` налаштовано; Compose має окремий volume. До 5 МБ, JPEG/PNG/WebP, до 25 Мп; backend перевіряє й перекодовує в JPEG без метаданих. Видача фото також потребує сесії; немає публічного static bucket.
- На login/register діє локальний ліміт 20 спроб / 15 хвилин / IP. Це ліміт одного процесу; розподілений limiter і очищення прострочених сесій — майбутнє розширення.

Фінансові метрики: `quantity × selling_price` — оцінка запасів, включно з резервом. Потенційна маржа розраховується тільки де відомі ціна й облікована собівартість деталі. Витрати на придбання донорів показуються окремо, щоб не віднімати їх удруге. Продажі та фактичний прибуток не моделюються. Грошові значення зберігаються як PostgreSQL NUMERIC(14,2), валюта UAH.

## API

Swagger: `/docs`; машинний контракт: `/openapi.json`. Повний endpoint-опис: [API.md](API.md).

Маршрути UI: `/`, `/vehicles`, `/catalog`, `/inventory`, `/operations`, `/analytics`, `/archive`, `/settings`. Незареєстрований користувач бачить авторизацію незалежно від маршруту. На телефоні — компактне меню, картки автомобілів/запчастин і одноколонкові форми; великі журнали прокручуються в межах таблиці.

## Тести

Backend-тести **очищають тестову БД**. Ніколи не використовуйте development- чи production-базу. `WAREHOUSE_TEST_DATABASE_URL` обов’язкова; назва має закінчуватися `_test` і проходити загальну перевірку Warehouse. Міграції тестуються на PostgreSQL, а не на SQLite.

```bash
cd warehouse
# Після створення .env:
docker compose --profile test up --build --abort-on-container-exit --exit-code-from tests tests
```

Профіль має окрему tmpfs-базу `db_test`, а не `warehouse_dev`. Без Docker для коду:

```bash
cd warehouse/backend
# Налаштуйте WAREHOUSE_TEST_DATABASE_URL на окрему warehouse*_test БД.
../.venv/bin/python -m pytest -q
```

Збірка frontend:

```bash
cd warehouse/frontend
npm ci
npm run build
```

Браузерний E2E створює **тільки тестові записи**. Запустіть backend на окремій `warehouse*_test` БД з вимкненими secure-cookie та Vite на 5173. Не запускайте його на звичайному складі. За потреби встановіть Chromium через `npx playwright install chromium`.

```bash
cd warehouse/frontend
WAREHOUSE_E2E=1 npm run test:e2e
# Якщо системний Chromium уже встановлено:
WAREHOUSE_E2E=1 WAREHOUSE_CHROMIUM_PATH=/usr/bin/chromium npm run test:e2e
```

Сценарій використовує справжній API: реєстрація, донор, перевірка/імпорт категорій, чекліст, надходження, резерв, фільтр аудиту, навігація, logout. Два viewport: desktop 1440×1000 та iPhone 390×844. Скриншоти — в ігнорованій `frontend/test-results/`. Після E2E очистьте тільки тестову БД повторним запуском backend-тестів.

Поточні результати й обмеження: [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md).

### Поточне хмарне середовище

Під час реалізації підготовлено `.venv`, встановлено npm-залежності, створено ігнорований `.env` із випадковим локальним паролем, а сервіс PostgreSQL `db` запущено через Compose. Фінальний локальний запуск працює повністю в Compose. Для ручного запуску спершу зупиніть його application-сервіси командою `docker compose stop backend frontend`, щоб звільнити порти. Після цього можна використати збережений локальний `.env` (не виводьте його значення):

```bash
cd warehouse/backend
set -a
source ../.env
set +a
../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

Frontend запускається стандартною командою з розділу вище. Процеси не слід вважати збереженими після завершення cloud-задачі. Це локальне тестування, не production-деплой.

### Docker-збірка в цьому cloud через довірений проксі

Для цієї машини потрібні доступна адреса HTTP(S)-проксі та системний CA bundle. Не вимикайте перевірку TLS. Опціональний helper передає стандартні proxy build-args, актуальний DNS-запис проксі та довірений CA через тимчасовий BuildKit secret; секрет і сертифікати не копіюються в образ.

```bash
cd warehouse
python3 scripts/build-cloud-images.py backend
python3 scripts/build-cloud-images.py frontend
docker compose up --no-build -d
docker compose --profile test up --no-build --abort-on-container-exit --exit-code-from tests tests
```

Якщо домашній каталог Docker read-only, задайте для Compose `DOCKER_CONFIG` і `BUILDX_CONFIG` у writable-каталозі (наприклад `/tmp/warehouse-docker-config` і `/tmp/warehouse-buildx`). Для звичайного локального Docker достатньо стандартного запуску; helper не потрібен. Для іншого корпоративного CA передайте `--ca /path/to/trusted-ca-bundle.crt`.

## Isolated Railway staging preview

See [RAILWAY_STAGING.md](RAILWAY_STAGING.md) for the separate three-service Railway setup, production Nginx frontend, same-origin HTTPS API proxy, private PostgreSQL volume, secure sessions, migration startup, and exact feature-branch deployment steps. Staging uses `deploy/railway/*.Dockerfile`; the original Dockerfiles/Compose above remain local development defaults. No Railway deployment is performed by the preparation or local checks.
