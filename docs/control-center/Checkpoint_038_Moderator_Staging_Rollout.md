# Checkpoint 038 — Moderator staging rollout: BLOCKED до міграції

18 листопада 2026, 09:30 Київ / 07:30 UTC.
Repo: `TsPa33/telegram-bot`, branch: `feature/carpot-crm-moderator`.
Погоджений target SHA та перевірений remote head до роботи:
`562c25a87537ca284d1007e57a3f1c9730f1694d`.
Власник погодив контрольований rollout без backup для тестового середовища.

**Підсумок: операторський доступ недоступний; міграція й deployment НЕ виконані.**
Зупинено відповідно до прямої умови власника. Несумісну schema-002 версію не запускали.
Цей checkpoint — єдина документаційна зміна; він не змінює погоджений release target.

## Перевірений Railway scope

Project `selfless-caring`: `ff2f3a14-2ffa-49ba-9b9d-9889ce98da5d`.
Environment `warehouse-staging`: `e9d04365-fc5a-4ba2-84a7-275c44580fe8`.

| Ресурс | Фактичний стан |
| --- | --- |
| CRM `carpot-control-preview` | Online, 1/1 running, SUCCESS |
| CRM service ID | `14ec32b1-c1dc-4362-be91-a3e608212832` |
| Чинний CRM deployment | `bbb79bfb-9dd5-44b1-8c8b-336f9a72bcb0` |
| Чинний фактичний build SHA із deployment metadata | `2057de3bf5be680a2407ac887d080c9e6b472b05` |
| CRM DB `carpot-control-preview-db` | Online, 1/1 running, SUCCESS |
| CRM DB service ID | `0911f049-2808-4d99-a395-87674ea127fd` |
| Чинний DB deployment | `a10a8a3d-cc12-4c3d-8557-b2ee051c1f2a` |
| Persistent volume | `1314c242-090a-4936-a8f8-7d98a6307529`, `/var/lib/postgresql/data`, 1024 MB |
| DB public TCP proxy | Відсутній |
| Staged/applying changes у warehouse-staging | Відсутні |

Live CRM config досі показує source branch `feature/carpot-control-center-warehouse`
і pinned `source.commitSha=472d9ad1339c7f714c7b350e98b2932765571650`.
Це відрізняється від фактичного `meta.commitHash=2057de3b` чинного deployment;
для release identity використано deployment metadata. Конфігурацію не виправляли.

## Конкретний блокер оператора

1. Доступний Railway connector автентифікований через OAuth. Для обох цільових
   сервісів `list_variables` повернув `valuesRedacted=true`: доступні назви,
   credentials/DB URLs не доступні. Sealed variables відсутні; жодні значення
   не відновлювали й не перезаписували.
2. У CRM service variable inventory немає `CONTROL_CENTER_MIGRATOR_URL` або
   `CONTROL_CENTER_OPERATOR_URL`; є лише чинний `CONTROL_CENTER_DATABASE_URL`
   runtime. Значення runtime URL також приховане. Це не доказ відсутності ролі
   migrator у PostgreSQL; її права неможливо перевірити цим доступом.
3. У поточному execution environment немає Railway CLI, Railway CLI auth config,
   `RAILWAY_TOKEN`, `RAILWAY_API_TOKEN` або `CONTROL_CENTER_*` credentials.
   Автентифікований SSH/операторський канал до приватної CRM DB недоступний.
4. Read-only discovery connector tunnels повернув:
   `Connector tunnels are not available for your account.`
   Доступні прямі Railway tools не надають SQL/exec/SSH для наявного migrator.

Наявний `app.control_center.manage.migrate()` явно використовує
`connection("CONTROL_CENTER_MIGRATOR_URL")`, перевіряє schema/environment,
бере advisory transaction lock і застосовує `002.sql` у транзакції.
Немає дозволеного автентифікованого каналу для виконання цієї команди з
операторською роллю в цільовій БД. Не створювали публічний DB proxy, додаткові
сервіси, pre-deploy workaround або DDL endpoint і не додавали migrator secret
до web runtime.

## Runtime verification: виконано й не виконано

System-trust HTTPS перевірка чинного staging origin:
`https://carpot-control-preview-warehouse-staging.up.railway.app`.

| Перевірка | Результат |
| --- | --- |
| GET `/health` | **200**, `{"status":"ok"}` |
| GET `/api/control/status` | **200**, enabled=true, environment=staging, auth_mode=password-only |
| GET `/api/control/auth/me` без staff session | **401** |
| SQL schema read / migration `001 → 002` | **NOT RUN**, немає operator channel |
| Новий deployment ID | **Відсутній** |
| Owner login і «Команда CRM» | **NOT VERIFIED**, rollout зупинено до міграції |
| Moderator permissions / contacts / queue / notes | **NOT VERIFIED на staging**, нова версія не deployed |
| Authenticated CSRF / клієнтські мутації | **NOT VERIFIED на staging** |

Чинна schema 001 випливає з exact deployed SHA 2057de3b та health 200:
його DB connection guard вимагає `("001", environment())`. Прямий SQL read
не виконувався; це inference із release provenance та runtime guard.
Попередній CI із Checkpoint 036 не видається за runtime acceptance цього rollout.
Backup не створювався; жодних SQL/DDL/DB mutation або credential reset не виконано.

## Незмінні межі

Повторний environment status показав усі 8 staging services Online, 0 issues,
0 recent failures та незмінні deployment IDs між двома status snapshots:

| Сервіс | Чинний deployment ID |
| --- | --- |
| carpot-control-preview | `bbb79bfb-9dd5-44b1-8c8b-336f9a72bcb0` |
| carpot-control-preview-db | `a10a8a3d-cc12-4c3d-8557-b2ee051c1f2a` |
| telegram-bot | `6fa3edf7-d037-4985-a0e7-2243f5655110` |
| confident-sparkle | `c0bb20ec-b1d9-4907-aee3-9ac473568f19` |
| warehouse-import-worker | `481bb395-9851-4fc2-b123-4562b83b7152` |
| carpot-billing-sandbox | `43cd9e65-4a47-41bf-998c-9a0a3926e16b` |
| Postgres-ADcL | `ec857870-5572-4a5b-920d-2aaf71dbdb22` |
| postgres | `77f27cee-f79c-460e-9f9f-31cb6cb3c936` |

Railway service/variable/deployment/database mutations у цьому пакеті: **0**.
Production перевірено read-only: worker/Postgres/Redis позначені Offline; є
старий pending REMOVING для worker deployment `0a1f9ef7-9608-465d-820f-1170410a77dd`
із датою 2026-05-19. До цього стану не втручалися; він не спричинений цим rollout.
Warehouse, Telegram, Billing та Production не змінювалися нашими діями.
Merge/main, нові сервіси та live staff accounts не створювалися.

## Умова продовження

Потрібен автентифікований операторський канал до **існуючої CRM DB**:
SSH/приватний operator execution із окремим `CONTROL_CENTER_MIGRATOR_URL`,
правами власника CRM schema та чинним TLS/CA. Передавати пароль або URL у чат
не потрібно; надається execution access/secure configuration.

Після його появи: перевірити точний environment/database/schema/role, підготувати
контрольоване вікно CRM, виконати на погодженому target SHA
`python -m app.control_center.manage migrate`, підтвердити schema 002 і збереження
staff IDs/audit, потім розгорнути **лише** `carpot-control-preview` та перевірити
Owner UI, Moderator RBAC, CSRF, clients і revocation. Погоджений target залишається
562c25a8. До підтвердженої міграції schema-002 runtime не запускати.
