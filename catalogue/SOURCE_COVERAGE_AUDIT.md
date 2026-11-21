# Повний source-coverage аудит CarPot (SELECT-only)

Мета: виміряти, скільки з усіх PRD source ID дійсно пов'язані з легковими модифікаціями в локальній MySQL `td1q2018`, для скількох марок/моделей/модифікацій. **Це не нормалізація українських назв і не заводська специфікація/BOM.** Нові canonical типи не створюються.

## Запуск на Windows

Виконувати в PowerShell із кореня checkout `C:\CarPot\telegram-bot`. Потрібен `PyMySQL`. Облікові дані `SOURCE_*` встановлюються для кожного нового сеансу PowerShell. Пароль не показувати й не зберігати у звітах.

```powershell
cd C:\CarPot\telegram-bot
$env:SOURCE_HOST = "127.0.0.1"
$env:SOURCE_PORT = "3306"
$env:SOURCE_USER = "root"
$env:SOURCE_PASSWORD = ""
$env:SOURCE_DATABASE = "td1q2018"

py -3 .\catalogue\source_coverage_audit.py preflight --output C:\CarPot\exports\source-coverage-v1
py -3 .\catalogue\source_coverage_audit.py scan --output C:\CarPot\exports\source-coverage-v1 --batch-size 20
```

Першу команду обов'язково виконати успішно перед другою. Якщо preflight повідомив, що індекс не перевірено, **не запускати повний скан**: спочатку перевірити існуючі індекси. Індекси/DDL на джерелі не створювати. Друга команда працює до завершення, друкує поточний `car_id` та обсяг опрацьованих автомобілів. Для пробного обмеженого запуску можна додати `--max-cars 1000`; `complete=false` у цьому разі означає лише частковий результат. Повторна команда `scan` із тим самим output автоматично продовжує з checkpoint. Параметр `--batch-size` можна зменшити до 10, якщо пакет завеликий.

## Артефакти у папці output

- `summary.json`: точні aggregate counts **тільки для пройденого діапазону**, `complete=true` лише якщо прочитано всі `passanger_cars`;
- `by_brand.csv`: кількість модифікацій, моделей і різних source PRD за виробником;
- `by_model.csv`: покриття моделей без генерації вигаданих сумісностей;
- `prd_coverage.csv`: всі джерельні PRD ID і скільки легкових моделей з ними пов'язано;
- `unknown_prd_ids.csv`: ID із article_links, відсутні у довіднику PRD;
- `audit.sqlite3`: локальний checkpoint і агреговані model→PRD зв'язки, без копії article/OEM/photo payload.

Звіт можна оновити без доступу до MySQL:

```powershell
py -3 .\catalogue\source_coverage_audit.py report --output C:\CarPot\exports\source-coverage-v1
```

**Метрики**: `prd_source_rows` — кількість сирих PRD рядків, не складських деталей; `prd_source_ids_linked_to_passenger_models` — PRD ID, присутні хоча б в одному джерельному зв'язку легкового автомобіля; `passenger_modifications_with_prd_links` — кількість модифікацій хоча б з одним зв'язком; `passenger_car_prd_link_pairs` — кількість різних пар автомобіль+тип PRD (пропозиції постачальників не множать тип); `new_canonical_types_approved=0` поки не відбулося owner review. OEM, фото, унікальні артикули та заводські комплектації цей аудит **не рахує**.

Сканування використовує тільки `SHOW`, `SELECT`, `SET SESSION` до локального джерела; файли SQLite/CSV/JSON пише **тільки на диск Windows**. Не підключається до Railway, не публікує, не змінює склад, не створює індексів. Для можливості перезапуску reference SHA-256 прив'язує стан до початкових makers/models/PRD; зміна цих таблиць під час повторного запуску потребує нового output. Без довгої транзакції MySQL результат не гарантує атомарного знімка всієї БД за час багатогодинного скану.
