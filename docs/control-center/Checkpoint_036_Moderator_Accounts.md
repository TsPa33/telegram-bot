# Checkpoint 036 — Moderator та персональні облікові записи CRM

17 листопада 2026, Київ. Issue #540, `TsPa33/telegram-bot`.
Базова CRM-гілка: `feature/carpot-control-center-warehouse`, Draft PR #539.
Актуальний GitHub head перевірено до роботи та перед push:
`2057de3bf5be680a2407ac887d080c9e6b472b05`.

Implementation SHA: `97a31c93089c3f7ac416ddba6682878686cbef26`.
Пакет опубліковано окремо в `feature/carpot-crm-moderator`, щоб не оновлювати
гілку розгорнутого staging. PR #539 і базова гілка не змінені.
Фінальний docs-only commit додає цей checkpoint після перевірки CI.

## Реалізація

- Додано `Moderator` до SQL CHECK, ORM, operator provisioning і staff update validator.
  `global_access` залишається лише Owner/Administrator. Окремі дозволи визначають
  глобальну видимість компаній, роботу з їхніми завданнями та адміністративне призначення.
- Moderator бачить усіх клієнтів поточного середовища, повні контакти за відповідного
  source evidence, нотатки та загальну чергу. Може створювати/редагувати нотатки,
  створювати власні завдання та оновлювати завдання інших співробітників у цьому середовищі.
- Moderator не має доступу до фінансів навіть із помилково встановленим finance flag;
  не читає staff registry/audit, не створює акаунти, не змінює ролі, company grants,
  адміністративні налаштування чи ключі інтеграцій. Особиста зміна пароля доступна.
  Support/Manager scopes і маскування контактів збережені.
- Owner-only створення персональних Moderator/Manager/Support, перегляд статусів,
  керування чинними ролями/доступом, блокування, розблокування та скидання доступу
  додано до «Безпека та налаштування → Команда CRM». Чинний owner-only PATCH збережено.
- Кожна привілейована дія потребує свіжого policy-bound step-up: пароль власника
  у password-only staging, новий одноразовий MFA-код у MFA-режимі. CSRF та Origin
  перевіряються чинним транспортом. Успішні зміни та metadata audit атомарні.
- Логін унікальний незалежно від регістру; SQL canonical unique index також захищає
  від конфліктів із legacy іменами. Нові логіни мають перевірений ASCII-формат.
  Публічного створення акаунтів або відправлення запрошень немає.

## Активація і сесії

Сервер генерує випадковий тимчасовий пароль, показує Owner лише у відповіді
створення/скидання і зберігає лише Argon2 hash. Пароль дійсний 24 години та
відкриває рівно одну 10-хвилинну restricted session, включно з конкурентними входами.
Повторно отримати цей пароль через staff list або reload неможливо.

До зміни пароля клієнти, контакти й черга закриті сервером. У MFA-режимі новий
співробітник додатково підключає власний Authenticator; encrypted enrollment
обмежений staff/session/purpose і 10 хвилинами. Restricted session не отримує
ознаку MFA verification. Після активації всі сесії відкликаються, потрібен новий
вхід з особистим паролем та MFA, якщо цього вимагає чинна політика.

Блокування, зміна ролі та reset відкликають усі сесії. Reset замінює пароль і MFA
матеріал та вимагає повторної активації; заблокований акаунт автоматично не активується.
Для майбутнього переходу акаунта з password-only на MFA потрібні owner reset
і нова активація з Authenticator; вимкнення MFA у production не додається.
Тіла нотаток, паролі та MFA seeds не записуються в audit. Plaintext credentials
не додавалися до GitHub, звітів або logs; invitation/credentials зовні не надсилалися.

## Перевірки

Локальні disposable PostgreSQL/API, жодних живих клієнтських даних:

- Цільові security/password/rotation/migration/projection/standalone tests: **69 PASS**,
  з них **13 нових** для Moderator/accounts. Останні зміни activation failure audit
  та session binding додатково перевірені повторним запуском цих 13 tests.
- Перевірено all-client/contact/task/note права, finance/admin 403, міжсередовищну
  ізоляцію, CSRF, disable/reset revocation, canonical uniqueness, одноразовий пароль
  під конкурентним навантаженням, MFA enrollment, атомарний rollback при помилці audit.
- Upgrade з реального SQL 001 до 002 зберігає staff ID, sessions і append-only audit;
  повторний migrate і заборонені runtime DDL/schema/audit mutations перевірені.
- TypeScript та standalone Vite CRM build: PASS; model unit: **5 PASS**.
- Chromium/WebKit × 320/1440: **4 PASS** owner provisioning → password activation →
  all clients/contacts/notes/queue → finance hidden → disable/reactivate/reset.
- Chromium/WebKit × 320/1440: **4 PASS** restricted MFA activation → personal password →
  власний Authenticator → повторний MFA login. Локальні browser libraries ізольовані
  у test workspace; CI встановлює стандартні Playwright dependencies.

Незалежний CI на implementation SHA:
[run 44120867515](https://github.com/TsPa33/telegram-bot/actions/runs/44120867515).

**SUCCESS**, exact head `97a31c93089c3f7ac416ddba6682878686cbef26`:

| Job / перевірка | Результат |
| --- | --- |
| staff-and-projections | **73 PASS** |
| browsers: чинний frontend prebuild + model unit | **275 + 5 PASS**, TypeScript/Vite PASS |
| browsers: чинна React matrix | **32 PASS** |
| browsers: resilience / scoped roles | **4 + 6 PASS** |
| browsers: нова MFA activation | **4 PASS** |
| browsers: чинна password-only matrix | **4 PASS** |
| browsers: нове owner/Moderator account management | **4 PASS** |
| standalone-image | **SUCCESS**, non-root staff-only smoke |
| billing-compatibility | **145 PASS** |
| warehouse-regressions | **SKIPPED**, явне `warehouse_full=false` |

Підсумки звірено з фактичними job logs, не лише зеленим статусом run.
Початковий CI 44119643723 виявив дубль тексту нотатки в завчасно змонтованому
прихованому textarea. Редактор тепер монтується лише на вимогу; чинний browser
assertion не послаблювали. Повторний CI вище перевірив виправлений код і всі
54 browser scenarios. Проміжний run 44120670965 скасовано до завершення після
розділення одноразових MFA-акаунтів нової activation matrix та resilience tests.
Повний Warehouse domain regression не запускався: доменні модулі не змінені.

## Інструкція власнику після погодженого rollout

1. Відкрити «Безпека та налаштування → Команда CRM» у власному Owner-акаунті.
2. Увести окремий логін співробітника, залишити роль Moderator, указати причину та
   підтвердити дію власним паролем/MFA. Логін не потрібно повідомляти через GitHub.
3. Передати одноразовий пароль особисто захищеним каналом і приховати його в UI.
4. Співробітник входить зі своїм логіном, змінює тимчасовий пароль, підключає власний
   Authenticator у MFA-режимі та входить знову. Якщо активацію перервано — Owner робить reset.
5. Для блокування відкрити «Керувати», зняти «Активний доступ», підтвердити й зберегти.
   Для відновлення встановити прапорець; за потреби окремо скинути доступ.

## Межі та наступний крок

Railway deployment, міграція живої БД та staging/runtime acceptance **не виконувалися**.
Deployment ID для цього пакета відсутній. Production, інші продукти, Warehouse
entitlement formulas, Directory sync, Billing/Telegram/Sites code та auth policy
configuration не змінені. Merge/main не виконано; Issue #540 лишається відкритим.

Після code review й окремого погодження власника потрібен координований rollout
**лише CRM у warehouse-staging**: явний operator migrate до 002, потім новий образ
і runtime acceptance. Новий runtime/health вимагає schema 002; старий runtime
очікує 001, тому це не rolling-compatible зміна readiness. Не застосовувати міграцію
окремо до працюючого старого сервісу без погодженого вікна переходу. Міграція не
запускається на startup, migrator credentials не додаються до web runtime.
Legacy canonical username collision зупиняє міграцію транзакційно без перейменування
чи видалення акаунтів. Старий образ не є автоматичним rollback для schema 002.
Після deployment власник створює реальний Moderator через UI; цей пакет не створює
живих облікових записів і не надає доступу анонімним користувачам.
