# Одноразовий backup PostgreSQL Warehouse staging

Підготовлено код і локальні тести. Реальний backup Railway, завантаження файлів,
нові сервіси, зміни Variables, deployment та staging-міграції НЕ виконувалися.
Наведені нижче віддалені команди — інструкція після окремого погодження.

## Де виконується команда

Використовується **наявний PostgreSQL-сервіс `postgres`** у середовищі
`warehouse-staging` існуючого Railway project. Новий сервіс не потрібен.
Скрипт вимагає PostgreSQL 16 server і client tools. Фактичну версію на вашому
deployment потрібно перевірити через --preflight; сервіс за його назвою не
перейменовується й не перестворюється. Образ postgres:16-alpine перевірено локально.
У поточному Warehouse API цих утиліт немає; його Dockerfile не змінено.

Скрипт `scripts/backup-staging.sh` приймає лише:

- `WAREHOUSE_DB_HOST`: один приватний hostname `*.railway.internal`;
- `WAREHOUSE_DB_PORT`: порт, типово 5432;
- `WAREHOUSE_DB_NAME`: окрема БД `warehouse*` або `carpot_warehouse*`;
- `WAREHOUSE_DB_USER` і `WAREHOUSE_DB_PASSWORD`.

Для віддаленого виконання він обов'язково перевіряє
`RAILWAY_ENVIRONMENT_NAME=warehouse-staging` та явний прапорець підтвердження.
Публічний hostname, список hostnames, неоднозначний WAREHOUSE_DATABASE_URL,
непідтримувана версія PostgreSQL та відсутня ревізія Alembic спричиняють відмову.
Не запускайте backup у production навіть для перевірки відмови.

У DB-сервісі можуть бути тільки POSTGRES_* замість WAREHOUSE_DB_*.
Локальний launcher `scripts/backup-railway.py` використовує наявні WAREHOUSE_DB_*
або створює їхні aliases **лише в середовищі одного дочірнього процесу**:
RAILWAY_PRIVATE_DOMAIN → HOST, POSTGRES_DB → NAME, POSTGRES_USER → USER,
POSTGRES_PASSWORD → PASSWORD. Railway Variables не створюються і не змінюються.

## Сумісність із Railway CLI і перевірка перед запуском

Перевірено вихідний код офіційного Railway CLI 5.71.0, commit
[b62467ef1b5303e3e340283ed96425dcf9612993](https://github.com/railwayapp/cli/tree/b62467ef1b5303e3e340283ed96425dcf9612993/src/commands/ssh):
`ssh` підтримує --project, --environment, --service та remote command після --.
Native SSH успадковує stdin/stdout; коли stdin/stdout не є TTY, використовується
`ssh -T`. Наш launcher дає PIPE для обох потоків, тому не просить термінал.
Не використовується припущення про SCP/SFTP або неіснуючий `railway download`.

У цьому cloud Railway CLI не встановлений; спроба встановлення офіційного npm
пакета завершилася невдалим postinstall binary download. Реальну SSH-сесію та
ваші deployment permissions не перевірено. Сумісність CLI-контракту перевірено
за кодом; весь sender/receiver та restore перевірено через локальний non-TTY exec.
Це не видається за перевірку живого Railway deployment.

На ВАШОМУ комп'ютері потрібні Python 3.10+, Railway CLI з цим SSH-контрактом,
авторизована сесія та вже налаштований SSH key/agent (без прихованих interactive
prompts). Спочатку виконайте локальні `railway --version` і `railway ssh --help`.
Не вимикайте SSH host-key verification, не додавайте debug logging.

Із warehouse/ прочитайте фактичний WAREHOUSE_DB_NAME у налаштуваннях Warehouse API
(не копіюйте й не друкуйте пароль). Ім'я сервісу postgres НЕ є іменем database.
Якщо в postgres POSTGRES_DB=railway, а Warehouse використовує warehouse_staging,
передайте --database warehouse_staging: це тільки alias в одному дочірньому
процесі, не зміна Railway Variables. Іншу БД або CarPot database не підставляйте.

Read-only preflight, який НЕ запускає pg_dump (після погодження віддаленого доступу):

```sh
python3 scripts/backup-railway.py \
  --project EXISTING_PROJECT_ID --service postgres \
  --database warehouse_staging --confirm warehouse-staging --preflight
```

Замініть project ID і database на перевірені значення. Launcher порівнює project
ID, environment warehouse-staging і RAILWAY_SERVICE_NAME=postgres всередині
контейнера; потім перевіряє private hostname, credentials presence, client/server
major version і доступність Alembic-ревізії через read-only SQL. Не переходьте до
backup при невдалому preflight. Не змінюйте server version чи схему, щоб обійти його.

## Backup і пряме отримання на локальний комп'ютер після погодження

Створіть приватний батьківський каталог поза Git, наприклад $HOME/Backups.
--download-to повинен указувати на НОВИЙ каталог: існуючий не перезаписується.

```sh
python3 scripts/backup-railway.py \
  --project EXISTING_PROJECT_ID --service postgres \
  --database warehouse_staging --confirm warehouse-staging \
  --download-to "$HOME/Backups/warehouse-staging-first-backup"
```

Це один remote backup і download без нового сервісу, bucket, public URL або TCP
Proxy. Виконуйте цю команду локально, не всередині Railway shell. Без --download-to
команда тільки створює тимчасовий remote backup і друкує його шлях.

Пароль визначається всередині віддаленого процесу: його немає в URL, argv,
тексті скрипта або stdout. Авторизований шифрований SSH передає службовий ASCII
Base64-протокол через PIPE. Немає raw binary dump у текстовому терміналі, shell
редиректу CLI stdout у .dump або copy/paste з web terminal. CLI output ніколи не
виводиться користувачу чи в application logs. На локальному диску декодуються
часткові файли; тільки при правильному розмірі, SHA-256, PGDMP magic, завершенні
обох frames та exit code 0 вони приймаються як .dump + revision із sidecars.
Каталог має 0700, файли 0600. Пошкодження/обрив/неочікуваний output видаляє локальний
частковий результат, а remote backup залишається для повторного отримання.
Ліміт одного dump — 5 GiB, Base64 додає приблизно 33% traffic overhead.

Повторне отримання вже створеного файла БЕЗ нового pg_dump:

```sh
python3 scripts/backup-railway.py \
  --project EXISTING_PROJECT_ID --service postgres --confirm warehouse-staging \
  --fetch-directory /tmp/warehouse-backup.XXXXXXXX \
  --download-to "$HOME/Backups/warehouse-staging-retry"
```

Підставте точний шлях попереднього запуску; directory зі stdout має 8 випадкових
символів. Існуючий backup не видаляється автоматично. Якщо download упав до
друку шляху, подивіться /tmp через авторизований shell саме цього DB deployment,
не запускаючи нове резервування й не читаючи dump у термінал.

Виконується:

```sh
pg_dump --format=custom --no-owner --no-acl --no-password \
  --lock-wait-timeout=30s --file=PRIVATE_TEMP_FILE
```

Пароль передається тільки через process environment PGPASSWORD, інші параметри
— через PGHOST/PGPORT/PGDATABASE/PGUSER. Використовуються read-only connections,
приватна мережа Railway та звичайний консистентний snapshot pg_dump.
Власники/ACL не застосовуються при відновленні; це не backup ролей кластера,
інших databases, Railway Variables, volume configuration або файлів фото.

Внутрішній PostgreSQL використовує WireGuard private network; libpq за замовчуванням
має sslmode=prefer, а вже заданий суворіший PGSSLMODE зберігається. Пряме отримання файла
використовує шифрований SSH, не TLS. Це прямо зазначений transport, не обхід
certificate verification і не public PostgreSQL access.

Під час backup не виконуйте міграції чи DDL. pg_dump бере read locks і створює
навантаження на staging. Зміни даних не виконуються. При зміні Alembic-ревізії
між початком і завершенням скрипт видаляє backup і завершується помилкою.

Результат — каталог `/tmp/warehouse-backup.XXXXXXXX` з правами 0700, файли 0600:

```text
warehouse-staging.dump
warehouse-staging.dump.sha256
source-revision.txt
source-revision.txt.sha256
```

Каталог розміщений у тимчасовому filesystem **DB-контейнера**, а не на volume
чи постійному диску Warehouse API. Це короткочасний буфер, не довготривале сховище:
redeploy/restart може його втратити. Виберіть прямий download ДО запуску.
Після успішного отримання/перевірки видаліть саме надрукований тимчасовий каталог
через авторизований shell DB-сервісу. Не використовуйте широкі wildcard-команди.
При звичайній помилці/SIGTERM скрипт сам видаляє часткові файли; після SIGKILL
або обриву контейнера перевірте залишки окремо, не припускайте автоматичного cleanup.

## Чи потрібне S3/R2-сховище

Для реалізованого прямого CLI-шляху — НІ. Він не потребує нового cloud storage,
публічних посилань, storage credentials чи зміни Railway Variables. Шифрування
цього шляху — SSH. Якщо політика вимагає саме TLS або у deployment немає SSH exec,
цей конкретний шлях не підходить; це потрібно встановити preflight до backup.
Не переходьте на відкритий HTTP endpoint/TCP Proxy.

Резервний варіант у такому разі: приватний S3/R2 bucket, HTTPS SDK з тимчасовими
STS credentials (разом із session token), право PutObject/GetObject тільки на
один prefix, TTL credentials і lifecycle короткого retention, SHA-256 manifest.
Authorization передається в headers, не query URL; public access і presigned
links заборонені. Це окрема інтеграція, яку зараз не підключали, бо прямий шлях
реалізовано та перевірено локально. Якщо SSH preflight буде неможливий, потрібні
погоджені endpoint/bucket/prefix і тимчасові повноваження перед S3/R2-запуском.
Не просіть/не надсилайте credentials у чат. Файли не мають потрапляти в логи.

## Локальна перевірка отриманого файла

Тримайте файли поза репозиторієм у каталозі 0700 на зашифрованому локальному диску;
dump містить приватні дані Warehouse, зокрема email та password hashes користувачів.
Не завантажуйте його у GitHub, чат, CI artifacts, звичайні application logs чи
незахищене cloud storage. Не перейменовуйте .dump без відповідного checksum sidecar.
`.gitignore` і `.dockerignore` додатково виключають backups/, *.dump*, *.backup,
*.pgdump; не використовуйте `git add -f` для backup.

З установленим pg_restore 16:

```sh
python3 scripts/verify-backup.py /PRIVATE/LOCAL/DIR/warehouse-staging.dump
```

Або з локальним Docker і наявним образом postgres:16-alpine:

```sh
python3 scripts/verify-backup.py /PRIVATE/LOCAL/DIR/warehouse-staging.dump --docker
```

Перевірка не підключається до БД: перевіряє приватні права, PGDMP magic, SHA-256,
`pg_restore --list`, потім повністю читає/декомпресує archive через
`pg_restore --no-owner --no-acl --file=/dev/null`. Docker verifier не має мережі.
Для окремого Docker config використовуйте --docker-config PATH.
Додатково в каталозі backup перевірте `sha256sum -c source-revision.txt.sha256`
(на macOS: `shasum -a 256 -c source-revision.txt.sha256`).

SHA-256 виявляє пошкодження, але не підтверджує походження недовіреного dump.
Отримуйте archive і sidecars через погоджений авторизований канал. Наявність TOC
і digest не замінює фактичного відновлення.

## Відновлення тільки в окрему тестову PostgreSQL

Приклад для **власного локального Docker context**, без відкритих портів, без
Railway URL/паролів. Ім'я контейнера має бути вільним; ніколи не підставляйте
існуючий staging/production container, volume чи database. Архів повинен бути
довіреним: pg_restore виконує SQL/function definitions із backup.

```sh
export POSTGRES_PASSWORD="$(openssl rand -hex 32)"
docker run -d --name warehouse-backup-restore-check --network none \
  --env POSTGRES_PASSWORD --env POSTGRES_DB=warehouse_restore_test postgres:16-alpine
unset POSTGRES_PASSWORD
docker exec warehouse-backup-restore-check pg_isready -h 127.0.0.1 -U postgres
```

Дочекайтеся readiness, потім:

```sh
docker exec -i warehouse-backup-restore-check pg_restore \
  --exit-on-error --single-transaction --no-owner --no-acl \
  -U postgres -d warehouse_restore_test < /PRIVATE/LOCAL/DIR/warehouse-staging.dump
```

Відновлення має завершитися з кодом 0. При помилці не продовжуйте з частково
відновленим станом; перевіряйте причину тільки в ізольованому target.

```sh
docker exec warehouse-backup-restore-check psql -X -U postgres -d warehouse_restore_test \
  -c "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
docker exec warehouse-backup-restore-check psql -X -U postgres -d warehouse_restore_test \
  -c "SELECT version_num FROM public.alembic_version;"
docker exec warehouse-backup-restore-check psql -X -U postgres -d warehouse_restore_test \
  -c "SELECT (SELECT count(*) FROM vehicles) AS vehicles, (SELECT count(*) FROM parts) AS parts, (SELECT count(*) FROM operations) AS operations;"
```

Очікуються accounts, sessions, vehicles, categories, parts, operations, photos,
alembic_version та всі інші таблиці source, якщо з'являться нові. Ревізія має
точно відповідати source-revision.txt. Для поточного Warehouse це може бути
f482ab1376c0 (без vehicles.ktype) або c91e72b6a410 (з nullable vehicles.ktype).
Backup НЕ застосовує staging-міграцію й не переводить стару схему на нову.

Зіставляйте дані з погодженим snapshot/baseline, враховуючи concurrent writes:
restore відтворює момент snapshot pg_dump, не всі записи після нього. Перевіряйте
зв'язки, резерви, NULL K-Type, аудит, triggers і бізнес-вибірки приватно. Не
виводьте рядки з email/password hashes у спільні логи. Якщо запускаєте застосунок
над restore target, спершу переконайтеся в сумісності code/schema; не спрямовуйте
його на робочу staging-БД. Після перевірки видаліть локальний target разом із
його одноразовим anonymous volume:

```sh
docker rm -f -v warehouse-backup-restore-check
```

## Автоматичні локальні тести

Із warehouse/backend:

```sh
PYTHONPATH=. ../.venv/bin/python -m pytest unit_tests/test_backup_tools.py -q
```

Із warehouse/:

```sh
python3 scripts/test-backup-local.py
```

Другий тест створює/видаляє тільки власні випадково названі локальні контейнери.
Source має loopback-порт, restore не має мережі. Поточний тест створює синтетичну
SQL/ORM-фікстуру з revision marker offline_fixture, БЕЗ команд Alembic і без
міграцій. Виконує справжній pg_dump, ТОЙ САМИЙ remote sender і локальний PIPE
receiver, SHA-256/full decode і restore в інший PostgreSQL. Порівнює всі таблиці,
рядки та revision marker, перевіряє immutable audit і незмінність source.
Штучно пошкоджений archive із перерахованим checksum також має відхилятися.
Локальні containers/volumes/backups видаляються. Паролі одноразові й не друкуються.

Unit-тести додатково покривають усі 256 byte values, CRLF transport, обрив,
неправильний digest/розмір/filename, nonzero CLI exit, повторний fetch без dump,
правильний postgres target і відмову при неправильному project/environment/service.
Це не заміна реального read-only preflight на вашому Railway.

Поточна локальна перевірка: 88 offline unit-тестів пройшли (28 — backup/transfer).
Реальний локальний custom dump пройшов той самий framed sender/receiver, SHA-256,
full decode та restore в окремий PostgreSQL; усі рядки, revision marker і audit
trigger збережено. Alembic-команди не запускалися. Gitleaks не виявив секретів.

Погодження потрібне перед реальним backup/download приватних staging-даних.
Скрипти не виконують deployment, commit/push або зміни Railway Variables,
production чи staging-схеми. Додаткове storage не потрібне для прямого SSH-шляху.
