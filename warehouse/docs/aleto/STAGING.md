# Aleto Catalogue v1: застосування в warehouse-staging

Це інструкція для майбутнього окремо дозволеного виконання. У цій задачі міграції та імпорт у Railway не запускалися, налаштування Railway не змінювалися.

## GitHub і Auto Deploy: поточні відомості

Перевірено origin гілки `feature/carpot-warehouse-mvp`: базовий remote SHA `df79988d9503869f037a090e1c9075f17a43dda4`. Локальні зміни обмежені `warehouse/`.

| Сервіс | Що відомо з файлів репозиторію | Живий Auto Deploy / isolation |
| --- | --- | --- |
| `warehouse-api` | `services.json`: ця гілка, `/warehouse`, backend Dockerfile; `STAGED_AUTO_DEPLOY.md`: Auto Deploy ON; startup `app.staging` автоматично застосовує міграції | Не підтверджено |
| `warehouse-web` | `services.json`: ця гілка, `/warehouse`, frontend Dockerfile; `STAGED_AUTO_DEPLOY.md`: Auto Deploy ON | Не підтверджено |
| `postgres` | `services.json`: окремий `postgres:16-alpine`, БД `warehouse_staging`, приватна мережа; не GitHub source | Не підтверджено |
| Інші сервіси, підключені до гілки | Локального повного реєстру немає | Перелічити й виключити production-зв'язки неможливо |

Це декларації, не результат перевірки Railway API. Railway-конектор і CLI відсутні, `RAILWAY_TOKEN` / `RAILWAY_API_TOKEN` не надано, стандартних локальних файлів авторизації Railway немає. GitHub Git-доступ працює, але не надає Railway-доступу. Офіційна документація Railway підтверджує, що push у підключену гілку автоматично запускає deployment: https://docs.railway.com/deployments/github-autodeploys (перевірено через офіційний `railwayapp/docs`, commit `514379fbde6325d56c7f0f61e1a985aea80e5e40`).

Відповідно до уточненої умови користувача: **лише локальний commit, push не виконується**, поки немає достовірного підтвердження ізольованого staging для всіх сервісів цієї гілки. Жодного `railway up`, Deploy, зміни Auto Deploy або публікації середовища не виконано. Перед майбутнім push потрібно перевірити у Railway Dashboard/API всі сервіси всіх доступних середовищ, пов'язані з цією гілкою, їхні фактичні DB bindings та відсутність production-зв'язків; локальні шаблони цього не замінюють.

## Дані поставляються з кодом

У Git входять:

- `warehouse/backend/app/data/aleto/v1/catalogue.sqlite3.gz` — 1 043 707 байтів, лише вихідні довідкові дані, без акаунтів, сесій чи Warehouse-БД.
- `warehouse/backend/app/data/aleto/v1/manifest.json` — кількості, моделі та контрольні суми.
- Міграція `warehouse/backend/alembic/versions/b8716962f6b8_aleto_reference_catalogue_v1.py`.
- Імпортер `warehouse/backend/app/services/aleto_import.py`.

Розпакований SHA-256: `c2cdde72685a6f41c70922e569fd8eae81e8bcbd292273fa411314dd920dccd3`.
SHA-256 gzip: `1b6eab050b283cdfa2f068a2e1f187fb525817e8cffed84a91a2b428b16e565a`.
Пакет містить **7 246 пропозицій, 10 112 модельних зв'язків, 14 400 вихідних шляхів категорій**. Він не залежить від `/workspace/scratch` чи локальної PostgreSQL. CLI без positional path використовує цей пакет, розпаковує у тимчасовий каталог і перевіряє обидві контрольні суми та кількості до записів у БД.

Наявний Dockerfile вже копіює `backend/app` до `/app/app`; пакет і manifest потраплять у майбутній backend-образ без змін Dockerfile або Watch Paths. Це не означає, що старий запущений образ staging уже містить нові файли.

## Перед виконанням

1. Окремо погодьте вікно staging-міграції/імпорту. Отримайте checkout **точного локального SHA, повідомленого в результаті задачі**, на maintenance-runner із доступом до приватної Warehouse staging-БД, або використайте backend-образ із цим SHA після окремо дозволеного розгортання. Поточний старий образ не замінюється цими інструкціями.
2. Використовуйте тільки існуючий `warehouse-staging` і його PostgreSQL. Не створюйте/перейменовуйте сервіси, не змінюйте production та не відкривайте БД публічно.
3. Змінні підключення мають бути інжектовані з **Warehouse staging API**, не зі спільних/production налаштувань. `WAREHOUSE_ENV=staging`, БД має назву `warehouse_staging` або `carpot_warehouse_staging`. Якщо є `RAILWAY_ENVIRONMENT_NAME`, він має дорівнювати `warehouse-staging`. Не підміняйте ці значення, щоб обійти guard.
4. Виберіть активний DIRECTOR workspace, не ID працівника. Отримайте ID наявного staging-директора через `/api/v1/auth/me` під його сесією. Не створюйте нового власника, якщо workspace вже існує.
5. Підготуйте перевірений backup саме staging-БД існуючим документованим процесом `warehouse/BACKUP_STAGING.md`. Не використовуйте downgrade як скасування даних імпорту: він видалить довідкові таблиці, але залишить доповнення спільного дерева категорій.

## Точні команди

Для maintenance-checkout виконуйте в `warehouse/backend` цього SHA з активним Python 3.11+ venv. Для нового погодженого backend-образу робочий каталог `/app`, залежності вже встановлені. Команди не виводять URL/паролі.

```bash
# Лише maintenance-checkout, якщо залежності ще не встановлені:
python -m pip install --require-hashes -r requirements.lock

# Установіть тільки workspace ID; секрети БД вже мають бути інжектовані.
export ALETO_ACCOUNT_ID='<ID наявного staging DIRECTOR workspace>'
: "${ALETO_ACCOUNT_ID:?Set the existing staging workspace ID}"

# Перевірка цільового середовища й локального пакета ДО міграції:
python - <<'PY'
import os
from app.config import database_url
from app.services.aleto_import import validate_target, load_package, BUNDLED_PACKAGE
validate_target(database_url(), os.getenv('WAREHOUSE_ENV', ''), True,
                os.getenv('RAILWAY_ENVIRONMENT_NAME'))
data = load_package(BUNDLED_PACKAGE)
assert (len(data['offers']), len(data['applications']), len(data['paths'])) == (7246, 10112, 14400)
print('Isolated staging target and bundled catalogue validated')
PY

# Схема (тільки після backup та погодження):
python -m alembic upgrade head
python -m alembic current
python -m alembic check
# Очікувана поточна ревізія цього checkout: b8716962f6b8.

# Попередній план; транзакція завжди відкочується:
python -m app.services.aleto_import --staging \
  --account-id "$ALETO_ACCOUNT_ID" --dry-run \
  --report /tmp/aleto-staging-dry-run.json
```

Перегляньте звіт: `input.offers=7246`, `input.applications=10112`, `input.taxonomy=14400`, `committed=false`. Існуючі категорії об'єднуються без перейменування/видалення. При неоднозначних/архівованих збігах зупиніться й розберіть відповідності; не очищайте таблиці для обходу перевірки. Кількість нових категорій на справжньому staging може відрізнятися від локальних 110 через наявний довідник.

```bash
# Явне застосування в staging:
python -m app.services.aleto_import --staging \
  --account-id "$ALETO_ACCOUNT_ID" --apply \
  --report /tmp/aleto-staging-apply.json

# Перевірка ідемпотентності без додаткових записів:
python -m app.services.aleto_import --staging \
  --account-id "$ALETO_ACCOUNT_ID" --dry-run \
  --report /tmp/aleto-staging-recheck.json

python - <<'PY'
import json
from pathlib import Path
r = json.loads(Path('/tmp/aleto-staging-recheck.json').read_text())
assert r['input'] == {'offers': 7246, 'applications': 10112, 'taxonomy': 14400}
assert all(v['inserted'] == v['updated'] == 0 for v in r['counts'].values())
assert r['committed'] is False
print('Staging catalogue present; repeat import has no changes')
PY
```

`--staging` сам по собі **не** означає apply. Без нього CLI дозволяє тільки окремі `warehouse*_test` / `carpot_warehouse*_test` БД. `WAREHOUSE_ENV=production`, production-назви БД та Railway environment `production` для staging-режиму відхиляються. Значення загального `DATABASE_URL` ігнорується — використовується лише Warehouse-конфігурація.

Перевірка через авторизований Warehouse UI/API: `/health` повертає 200; для Volvo XC40/XC60/XC90 `GET /api/v1/vehicles/{id}/aleto-catalog` дає 1 472 / 4 155 / 4 485 пропозицій цього пакета за відсутності інших імпортів Aleto. Джерела/зв'язки з попередніх додаткових імпортів зберігаються. Перевірте пошук OEM/артикулу, категорії, окремий напис довідкової ціни й timestamp. `Комп` залишається pending (139 вихідних шляхів), відсутні ціни — NULL; річна/VIN-сумісність не підтверджується.

Довідник діє для обраного workspace. Для іншого staging workspace виконується окремий явний імпорт із його DIRECTOR ID; глобального перезапису акаунтів немає. Залишки та продажні ціни не формуються імпортером.
